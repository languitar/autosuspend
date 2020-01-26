import configparser
import copy
from datetime import datetime, timedelta, timezone
import glob
from io import BytesIO
import json
import os
import pwd
import re
import socket
import subprocess
import time
from typing import Any, Dict, Iterable, Optional, Pattern, Sequence, Tuple
import warnings

import psutil

from . import Activity, Check, ConfigurationError, SevereCheckError, TemporaryCheckError
from .util import CommandMixin, NetworkMixin, XPathMixin
from ..util.systemd import list_logind_sessions


class ActiveCalendarEvent(NetworkMixin, Activity):
    """Determines activity by checking against events in an icalendar file."""

    def __init__(self, name: str, **kwargs) -> None:
        NetworkMixin.__init__(self, **kwargs)
        Activity.__init__(self, name)

    def check(self) -> Optional[str]:
        from ..util.ical import list_calendar_events

        response = self.request()
        start = datetime.now(timezone.utc)
        end = start + timedelta(minutes=1)
        events = list_calendar_events(BytesIO(response.content), start, end)
        self.logger.debug(
            "Listing active events between %s and %s returned %s events",
            start,
            end,
            len(events),
        )
        if events:
            return "Calendar event {} is active".format(events[0])
        else:
            return None


class ActiveConnection(Activity):
    """Checks if a client connection exists on specified ports."""

    @classmethod
    def create(
        cls, name: str, config: configparser.SectionProxy,
    ) -> "ActiveConnection":
        try:
            split_ports = config["ports"].split(",")
            ports = {int(p.strip()) for p in split_ports}
            return cls(name, ports)
        except KeyError as error:
            raise ConfigurationError("Missing option ports") from error
        except ValueError as error:
            raise ConfigurationError("Ports must be integers") from error

    def __init__(self, name: str, ports: Iterable[int]) -> None:
        Activity.__init__(self, name)
        self._ports = ports

    def check(self) -> Optional[str]:
        own_addresses = [
            (item.family, item.address.split("%")[0])
            for sublist in psutil.net_if_addrs().values()
            for item in sublist
        ]
        connected = [
            c.laddr[1]
            for c in psutil.net_connections()
            if (
                (c.family, c.laddr[0]) in own_addresses
                and c.status == "ESTABLISHED"
                and c.laddr[1] in self._ports
            )
        ]
        if connected:
            return "Ports {} are connected".format(connected)
        else:
            return None


class ExternalCommand(CommandMixin, Activity):
    def __init__(self, name: str, command: str) -> None:
        CommandMixin.__init__(self, command)
        Check.__init__(self, name)

    def check(self) -> Optional[str]:
        try:
            subprocess.check_call(self._command, shell=True)  # noqa: S602
            return "Command {} succeeded".format(self._command)
        except subprocess.CalledProcessError:
            return None


def _add_default_kodi_url(config: configparser.SectionProxy) -> None:
    if "url" not in config:
        config["url"] = "http://localhost:8080/jsonrpc"


class Kodi(NetworkMixin, Activity):
    @classmethod
    def collect_init_args(cls, config: configparser.SectionProxy) -> Dict[str, Any]:
        try:
            _add_default_kodi_url(config)
            args = NetworkMixin.collect_init_args(config)
            args["suspend_while_paused"] = config.getboolean(
                "suspend_while_paused", fallback=False
            )
            return args
        except ValueError as error:
            raise ConfigurationError("Configuration error {}".format(error)) from error

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "Kodi":
        return cls(name, **cls.collect_init_args(config))

    def __init__(
        self, name: str, url: str, suspend_while_paused: bool = False, **kwargs
    ) -> None:
        self._suspend_while_paused = suspend_while_paused
        if self._suspend_while_paused:
            request = url + (
                '?request={"jsonrpc": "2.0", "id": 1, '
                '"method": "XBMC.GetInfoBooleans",'
                '"params": {"booleans": ["Player.Playing"]} }'
            )
        else:
            request = url + (
                '?request={"jsonrpc": "2.0", "id": 1, '
                '"method": "Player.GetActivePlayers"}'
            )
        NetworkMixin.__init__(self, url=request, **kwargs)
        Activity.__init__(self, name)

    def check(self) -> Optional[str]:
        try:
            reply = self.request().json()
            if self._suspend_while_paused:
                if reply["result"]["Player.Playing"]:
                    return "Kodi actively playing media"
            else:
                if reply["result"]:
                    return "Kodi currently playing"
            return None
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise TemporaryCheckError(error) from error


class KodiIdleTime(NetworkMixin, Activity):
    @classmethod
    def collect_init_args(cls, config: configparser.SectionProxy) -> Dict[str, Any]:
        try:
            _add_default_kodi_url(config)
            args = NetworkMixin.collect_init_args(config)
            args["idle_time"] = config.getint("idle_time", fallback=120)
            return args
        except ValueError as error:
            raise ConfigurationError("Configuration error " + str(error)) from error

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "KodiIdleTime":
        return cls(name, **cls.collect_init_args(config))

    def __init__(self, name: str, url: str, idle_time: int, **kwargs) -> None:
        request = url + (
            '?request={{"jsonrpc": "2.0", "id": 1, '
            '"method": "XBMC.GetInfoBooleans",'
            '"params": {{"booleans": ["System.IdleTime({})"]}}}}'.format(idle_time)
        )
        NetworkMixin.__init__(self, url=request, **kwargs)
        Activity.__init__(self, name)
        self._idle_time = idle_time

    def check(self) -> Optional[str]:
        try:
            reply = self.request().json()
            if not reply["result"]["System.IdleTime({})".format(self._idle_time)]:
                return "Someone interacts with Kodi"
            else:
                return None
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise TemporaryCheckError(error) from error


class Load(Activity):
    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "Load":
        try:
            return cls(name, config.getfloat("threshold", fallback=2.5))
        except ValueError as error:
            raise ConfigurationError(
                "Unable to parse threshold as float: {}".format(error)
            ) from error

    def __init__(self, name: str, threshold: float) -> None:
        Check.__init__(self, name)
        self._threshold = threshold

    def check(self) -> Optional[str]:
        loadcurrent = os.getloadavg()[1]
        self.logger.debug("Load: %s", loadcurrent)
        if loadcurrent > self._threshold:
            return "Load {} > threshold {}".format(loadcurrent, self._threshold)
        else:
            return None


class Mpd(Activity):
    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "Mpd":
        try:
            host = config.get("host", fallback="localhost")
            port = config.getint("port", fallback=6600)
            timeout = config.getint("timeout", fallback=5)
            return cls(name, host, port, timeout)
        except ValueError as error:
            raise ConfigurationError(
                "Host port or timeout configuration wrong: {}".format(error)
            ) from error

    def __init__(self, name: str, host: str, port: int, timeout: float) -> None:
        Check.__init__(self, name)
        self._host = host
        self._port = port
        self._timeout = timeout

    def _get_state(self) -> Dict:
        from mpd import MPDClient

        client = MPDClient()
        client.timeout = self._timeout
        client.connect(self._host, self._port)
        state = client.status()
        client.close()
        client.disconnect()
        return state

    def check(self) -> Optional[str]:
        from mpd import MPDError

        try:
            state = self._get_state()
            if state["state"] == "play":
                return "MPD currently playing"
            else:
                return None
        except (MPDError, ConnectionError, socket.timeout, socket.gaierror) as error:
            raise TemporaryCheckError(error) from error


class NetworkBandwidth(Activity):
    @classmethod
    def create(
        cls, name: str, config: configparser.SectionProxy,
    ) -> "NetworkBandwidth":
        try:
            interfaces = config["interfaces"].split(",")
            interfaces = [i.strip() for i in interfaces if i.strip()]
            if not interfaces:
                raise ConfigurationError("No interfaces configured")
            host_interfaces = psutil.net_if_addrs().keys()
            for interface in interfaces:
                if interface not in host_interfaces:
                    raise ConfigurationError(
                        "Network interface {} does not exist".format(interface)
                    )
            threshold_send = config.getfloat("threshold_send", fallback=100)
            threshold_receive = config.getfloat("threshold_receive", fallback=100)
            return cls(name, interfaces, threshold_send, threshold_receive)
        except KeyError as error:
            raise ConfigurationError(
                "Missing configuration key: {}".format(error)
            ) from error
        except ValueError as error:
            raise ConfigurationError(
                "Threshold in wrong format: {}".format(error)
            ) from error

    def __init__(
        self,
        name: str,
        interfaces: Iterable[str],
        threshold_send: float,
        threshold_receive: float,
    ) -> None:
        Check.__init__(self, name)
        self._interfaces = interfaces
        self._threshold_send = threshold_send
        self._threshold_receive = threshold_receive
        self._previous_values = psutil.net_io_counters(pernic=True)
        self._previous_time = time.time()

    def check(self) -> Optional[str]:
        # acquire the previous state and preserve it
        old_values = self._previous_values
        old_time = self._previous_time

        # read new values and store them for the next iteration
        new_values = psutil.net_io_counters(pernic=True)
        self._previous_values = new_values
        new_time = time.time()
        if new_time == self._previous_time:
            raise TemporaryCheckError("Called too fast, no time between calls")
        self._previous_time = new_time

        for interface in self._interfaces:
            if interface not in new_values or interface not in self._previous_values:
                raise TemporaryCheckError("Interface {} is missing".format(interface))

            # send direction
            delta_send = (
                new_values[interface].bytes_sent - old_values[interface].bytes_sent
            )
            rate_send = delta_send / (new_time - old_time)
            if rate_send > self._threshold_send:
                return (
                    "Interface {} sending rate {} byte/s "
                    "higher than threshold {}".format(
                        interface, rate_send, self._threshold_send
                    )
                )

            # receive direction
            delta_receive = (
                new_values[interface].bytes_recv - old_values[interface].bytes_recv
            )
            rate_receive = delta_receive / (new_time - old_time)
            if rate_receive > self._threshold_receive:
                return (
                    "Interface {} receive rate {} byte/s "
                    "higher than threshold {}".format(
                        interface, rate_receive, self._threshold_receive
                    )
                )

        return None


class Ping(Activity):
    """Check if one or several hosts are reachable via ping."""

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "Ping":
        try:
            hosts = config["hosts"].split(",")
            hosts = [h.strip() for h in hosts]
            return cls(name, hosts)
        except KeyError as error:
            raise ConfigurationError(
                "Unable to determine hosts to ping: {}".format(error)
            ) from error

    def __init__(self, name: str, hosts: Iterable[str]) -> None:
        Check.__init__(self, name)
        self._hosts = hosts

    def check(self) -> Optional[str]:
        for host in self._hosts:
            cmd = ["ping", "-q", "-c", "1", host]
            if (
                subprocess.call(  # noqa: S603 we know the input from the config
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                == 0
            ):
                self.logger.debug("host " + host + " appears to be up")
                return "Host {} is up".format(host)
        return None


class Processes(Activity):
    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "Processes":
        try:
            processes = config["processes"].split(",")
            processes = [p.strip() for p in processes]
            return cls(name, processes)
        except KeyError as error:
            raise ConfigurationError("No processes to check specified") from error

    def __init__(self, name: str, processes: Iterable[str]) -> None:
        Check.__init__(self, name)
        self._processes = processes

    def check(self) -> Optional[str]:
        for proc in psutil.process_iter():
            try:
                pinfo = proc.name()
                for name in self._processes:
                    if pinfo == name:
                        return "Process {} is running".format(name)
            except psutil.NoSuchProcess:
                pass
        return None


class Smb(Activity):
    @classmethod
    def create(cls, name: str, config: Optional[configparser.SectionProxy]) -> "Smb":
        return cls(name)

    def check(self) -> Optional[str]:
        try:
            status_output = subprocess.check_output(  # noqa: S603, S607
                ["smbstatus", "-b"]
            ).decode("utf-8")
        except subprocess.CalledProcessError as error:
            raise SevereCheckError(error) from error

        self.logger.debug("Received status output:\n%s", status_output)

        connections = []
        start_seen = False
        for line in status_output.splitlines():
            if start_seen:
                connections.append(line)
            else:
                if line.startswith("----"):
                    start_seen = True

        if connections:
            return "SMB clients are connected:\n{}".format("\n".join(connections))
        else:
            return None


class Users(Activity):
    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "Users":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            try:
                user_regex = re.compile(config.get("name", fallback=r".*"))
                terminal_regex = re.compile(config.get("terminal", fallback=r".*"))
                host_regex = re.compile(config.get("host", fallback=r".*"))
                return cls(name, user_regex, terminal_regex, host_regex)
            except re.error as error:
                raise ConfigurationError(
                    "Regular expression is invalid: {}".format(error),
                ) from error

    def __init__(
        self,
        name: str,
        user_regex: Pattern,
        terminal_regex: Pattern,
        host_regex: Pattern,
    ) -> None:
        Activity.__init__(self, name)
        self._user_regex = user_regex
        self._terminal_regex = terminal_regex
        self._host_regex = host_regex

    def check(self) -> Optional[str]:
        for entry in psutil.users():
            if (
                self._user_regex.fullmatch(entry.name) is not None
                and self._terminal_regex.fullmatch(entry.terminal) is not None
                and self._host_regex.fullmatch(entry.host) is not None
            ):
                self.logger.debug(
                    "User %s on terminal %s from host %s " "matches criteria.",
                    entry.name,
                    entry.terminal,
                    entry.host,
                )
                return (
                    "User {user} is logged in on terminal {terminal} "
                    "from {host} since {started}".format(
                        user=entry.name,
                        terminal=entry.terminal,
                        host=entry.host,
                        started=entry.started,
                    )
                )
        return None


class XIdleTime(Activity):
    """Check that local X display have been idle long enough."""

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "XIdleTime":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            try:
                return cls(
                    name,
                    config.getint("timeout", fallback=600),
                    config.get("method", fallback="sockets"),
                    re.compile(config.get("ignore_if_process", fallback=r"a^")),
                    re.compile(config.get("ignore_users", fallback=r"a^")),
                )
            except re.error as error:
                raise ConfigurationError(
                    "Regular expression is invalid: {}".format(error),
                ) from error
            except ValueError as error:
                raise ConfigurationError(
                    "Unable to parse configuration: {}".format(error),
                ) from error

    def __init__(
        self,
        name: str,
        timeout: float,
        method: str,
        ignore_process_re: Pattern,
        ignore_users_re: Pattern,
    ) -> None:
        Activity.__init__(self, name)
        self._timeout = timeout
        if method == "sockets":
            self._provide_sessions = self._list_sessions_sockets
        elif method == "logind":
            self._provide_sessions = self._list_sessions_logind
        else:
            raise ValueError("Unknown session discovery method {}".format(method))
        self._ignore_process_re = ignore_process_re
        self._ignore_users_re = ignore_users_re

    def _list_sessions_sockets(self) -> Sequence[Tuple[int, str]]:
        """List running X sessions by iterating the X sockets.

        This method assumes that X servers are run under the users using the
        server.
        """
        sockets = glob.glob("/tmp/.X11-unix/X*")
        self.logger.debug("Found sockets: %s", sockets)

        results = []
        for sock in sockets:
            # determine the number of the X display
            try:
                display = int(sock[len("/tmp/.X11-unix/X") :])
            except ValueError:
                self.logger.warning(
                    "Cannot parse display number from socket %s. Skipping.",
                    sock,
                    exc_info=True,
                )
                continue

            # determine the user of the display
            try:
                user = pwd.getpwuid(os.stat(sock).st_uid).pw_name
            except (FileNotFoundError, KeyError):
                self.logger.warning(
                    "Cannot get the owning user from socket %s. Skipping.",
                    sock,
                    exc_info=True,
                )
                continue

            results.append((display, user))

        return results

    def _list_sessions_logind(self) -> Sequence[Tuple[int, str]]:
        """List running X sessions using logind.

        This method assumes that a ``Display`` variable is set in the logind
        sessions.
        """
        results = []
        for session_id, properties in list_logind_sessions():
            if "Name" in properties and "Display" in properties:
                try:
                    results.append(
                        (
                            int(properties["Display"].replace(":", "")),
                            str(properties["Name"]),
                        )
                    )
                except ValueError:
                    self.logger.warning(
                        "Unable to parse display from session properties %s",
                        properties,
                        exc_info=True,
                    )
            else:
                self.logger.debug(
                    "Skipping session %s because it does not contain "
                    "a user name and a display",
                    session_id,
                )
        return results

    def _is_skip_process_running(self, user: str) -> bool:
        user_processes = []
        for process in psutil.process_iter():
            try:
                if process.username() == user:
                    user_processes.append(process.name())
            except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                # ignore processes which have disappeared etc.
                pass

        for process in user_processes:
            if self._ignore_process_re.match(process) is not None:
                self.logger.debug(
                    "Process %s with pid %s matches the ignore regex '%s'."
                    " Skipping idle time check for this user.",
                    process.name(),
                    process.pid,
                    self._ignore_process_re,
                )
                return True

        return False

    def check(self) -> Optional[str]:
        for display, user in self._provide_sessions():
            self.logger.info("Checking display %s of user %s", display, user)

            # check whether this users should be ignored completely
            if self._ignore_users_re.match(user) is not None:
                self.logger.debug("Skipping user '%s' due to request", user)
                continue

            # check whether any of the running processes of this user matches
            # the ignore regular expression. In that case we skip idletime
            # checking because we assume the user has a process running that
            # inevitably tampers with the idle time.
            if self._is_skip_process_running(user):
                continue

            # prepare the environment for the xprintidle call
            env = copy.deepcopy(os.environ)
            env["DISPLAY"] = ":{}".format(display)
            env["XAUTHORITY"] = os.path.join(
                os.path.expanduser("~" + user), ".Xauthority"
            )

            try:
                idle_time_output = subprocess.check_output(  # noqa: S603, S607
                    ["sudo", "-u", user, "xprintidle"], env=env
                )
                idle_time = float(idle_time_output.strip()) / 1000.0
            except (subprocess.CalledProcessError, ValueError) as error:
                self.logger.warning(
                    "Unable to determine the idle time for display %s.",
                    display,
                    exc_info=True,
                )
                raise TemporaryCheckError(error) from error

            self.logger.debug(
                "Idle time for display %s of user %s is %s seconds.",
                display,
                user,
                idle_time,
            )

            if idle_time < self._timeout:
                return (
                    "X session {} of user {} "
                    "has idle time {} < threshold {}".format(
                        display, user, idle_time, self._timeout
                    )
                )

        return None


class LogindSessionsIdle(Activity):
    """Prevents suspending in case a logind session is marked not idle.

    The decision is based on the ``IdleHint`` property of logind sessions.
    """

    @classmethod
    def create(
        cls, name: str, config: configparser.SectionProxy,
    ) -> "LogindSessionsIdle":
        types = config.get("types", fallback="tty,x11,wayland").split(",")
        types = [t.strip() for t in types]
        states = config.get("states", fallback="active,online").split(",")
        states = [t.strip() for t in states]
        return cls(name, types, states)

    def __init__(self, name: str, types: Iterable[str], states: Iterable[str]) -> None:
        Activity.__init__(self, name)
        self._types = types
        self._states = states

    def check(self) -> Optional[str]:
        for session_id, properties in list_logind_sessions():
            self.logger.debug("Session %s properties: %s", session_id, properties)

            if properties["Type"] not in self._types:
                self.logger.debug(
                    "Ignoring session of wrong type %s", properties["Type"]
                )
                continue
            if properties["State"] not in self._states:
                self.logger.debug(
                    "Ignoring session because its state is %s", properties["State"]
                )
                continue

            if not properties["IdleHint"]:
                return "Login session {} is not idle".format(session_id)

        return None


class XPath(XPathMixin, Activity):
    def __init__(self, name: str, **kwargs) -> None:
        Activity.__init__(self, name)
        XPathMixin.__init__(self, **kwargs)

    def check(self) -> Optional[str]:
        if self.evaluate():
            return "XPath matches for url " + self._url
        else:
            return None
