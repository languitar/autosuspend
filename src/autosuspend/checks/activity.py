import configparser
from contextlib import suppress
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from textwrap import shorten
import time
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Pattern,
    Tuple,
    TYPE_CHECKING,
)
import warnings

import psutil

from . import Activity, Check, ConfigurationError, SevereCheckError, TemporaryCheckError
from .util import CommandMixin, NetworkMixin
from ..util.subprocess import raise_severe_if_command_not_found
from ..util.systemd import LogindDBusException
from ..util.xorg import list_sessions_logind, list_sessions_sockets, XorgSession


if TYPE_CHECKING:
    from jsonpath_ng import JSONPath

# isort: off

with suppress(ModuleNotFoundError):
    from .ical import ActiveCalendarEvent  # noqa
with suppress(ModuleNotFoundError):
    from .xpath import XPathActivity as XPath  # noqa
with suppress(ModuleNotFoundError):
    from .systemd import LogindSessionsIdle  # noqa

from .kodi import Kodi, KodiIdleTime  # noqa

# isort: on


class ActiveConnection(Activity):
    """Checks if a client connection exists on specified ports."""

    @classmethod
    def create(
        cls,
        name: str,
        config: configparser.SectionProxy,
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

    def normalize_address(
        self, family: socket.AddressFamily, address: str
    ) -> Tuple[socket.AddressFamily, str]:
        if family == socket.AF_INET6:
            # strip scope
            return family, address.split("%")[0]
        elif family == socket.AF_INET:
            # convert to IPv6 to handle cases where an IPv4 address is targeted via IPv6
            # to IPv4 mapping
            return socket.AF_INET6, f"::ffff:{address}"
        else:
            return family, address

    def check(self) -> Optional[str]:
        # Find the addresses of the system
        own_addresses = [
            self.normalize_address(item.family, item.address)
            for sublist in psutil.net_if_addrs().values()
            for item in sublist
        ]
        # Find established connections to target ports
        connected = [
            connection.laddr[1]
            for connection in psutil.net_connections()
            if (
                self.normalize_address(connection.family, connection.laddr[0])
                in own_addresses
                and connection.status == "ESTABLISHED"
                and connection.laddr[1] in self._ports
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
        except subprocess.CalledProcessError as error:
            raise_severe_if_command_not_found(error)
            return None


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
            raise TemporaryCheckError("Unable to get the current MPD state") from error


class NetworkBandwidth(Activity):
    @classmethod
    def _ensure_interfaces_exist(cls, interfaces: Iterable[str]) -> None:
        host_interfaces = psutil.net_if_addrs().keys()
        for interface in interfaces:
            if interface not in host_interfaces:
                raise ConfigurationError(
                    "Network interface {} does not exist".format(interface)
                )

    @classmethod
    def _extract_interfaces(cls, config: configparser.SectionProxy) -> List[str]:
        interfaces = config["interfaces"].split(",")
        interfaces = [i.strip() for i in interfaces if i.strip()]
        if not interfaces:
            raise ConfigurationError("No interfaces configured")
        cls._ensure_interfaces_exist(interfaces)
        return interfaces

    @classmethod
    def create(
        cls,
        name: str,
        config: configparser.SectionProxy,
    ) -> "NetworkBandwidth":
        try:
            interfaces = cls._extract_interfaces(config)
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

    @classmethod
    def _rate(cls, new: float, old: float, new_time: float, old_time: float) -> float:
        delta = new - old
        return delta / (new_time - old_time)

    class _InterfaceActive(RuntimeError):
        pass

    def _check_interface(
        self,
        interface: str,
        new: psutil._common.snetio,
        old: psutil._common.snetio,
        new_time: float,
        old_time: float,
    ) -> None:
        # send direction
        rate_send = self._rate(new.bytes_sent, old.bytes_sent, new_time, old_time)
        if rate_send > self._threshold_send:
            raise self._InterfaceActive(
                "Interface {} sending rate {} byte/s "
                "higher than threshold {}".format(
                    interface, rate_send, self._threshold_send
                )
            )

        # receive direction
        rate_receive = self._rate(new.bytes_recv, old.bytes_recv, new_time, old_time)
        if rate_receive > self._threshold_receive:
            raise self._InterfaceActive(
                "Interface {} receive rate {} byte/s "
                "higher than threshold {}".format(
                    interface, rate_receive, self._threshold_receive
                )
            )

    def check(self) -> Optional[str]:
        # acquire the previous state and preserve it
        old_values = self._previous_values
        old_time = self._previous_time

        # read new values and store them for the next iteration
        new_values = psutil.net_io_counters(pernic=True)
        self._previous_values = new_values
        new_time = time.time()
        if new_time <= self._previous_time:
            raise TemporaryCheckError("Called too fast, no time between calls")
        self._previous_time = new_time

        for interface in self._interfaces:
            if interface not in new_values or interface not in self._previous_values:
                raise TemporaryCheckError("Interface {} is missing".format(interface))

            try:
                self._check_interface(
                    interface,
                    new_values[interface],
                    old_values[interface],
                    new_time,
                    old_time,
                )
            except self._InterfaceActive as e:
                return str(e)

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
        try:
            for host in self._hosts:
                cmd = ["ping", "-q", "-c", "1", host]
                if (
                    subprocess.call(  # noqa: S603 we know the input from the config
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    == 0
                ):
                    self.logger.debug("host " + host + " appears to be up")
                    return "Host {} is up".format(host)
            return None
        except FileNotFoundError as error:
            raise SevereCheckError("Binary ping cannot be found") from error


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
            with suppress(psutil.NoSuchProcess):
                pinfo = proc.name()
                if pinfo in self._processes:
                    return "Process {} is running".format(pinfo)
        return None


class Smb(Activity):
    @classmethod
    def create(cls, name: str, config: Optional[configparser.SectionProxy]) -> "Smb":
        return cls(name)

    def _safe_get_status(self) -> str:
        try:
            return subprocess.check_output(  # noqa: S603, S607
                ["smbstatus", "-b"]
            ).decode("utf-8")
        except FileNotFoundError as error:
            raise SevereCheckError("smbstatus binary not found") from error
        except subprocess.CalledProcessError as error:
            raise TemporaryCheckError("Unable to execute smbstatus") from error

    def check(self) -> Optional[str]:
        status_output = self._safe_get_status()

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

    @staticmethod
    def _get_session_method(method: str) -> Callable[[], List[XorgSession]]:
        if method == "sockets":
            return list_sessions_sockets
        elif method == "logind":
            return list_sessions_logind
        else:
            raise ValueError("Unknown session discovery method {}".format(method))

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
        self._provide_sessions: Callable[[], List[XorgSession]]
        self._provide_sessions = self._get_session_method(method)
        self._ignore_process_re = ignore_process_re
        self._ignore_users_re = ignore_users_re

    @staticmethod
    def _get_user_processes(user: str) -> List[psutil.Process]:
        user_processes = []
        for process in psutil.process_iter():
            with suppress(
                psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied
            ):
                if process.username() == user:
                    user_processes.append(process.name())
        return user_processes

    def _is_skip_process_running(self, user: str) -> bool:
        for process in self._get_user_processes(user):
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

    def _safe_provide_sessions(self) -> List[XorgSession]:
        try:
            return self._provide_sessions()
        except LogindDBusException as error:
            raise TemporaryCheckError(error) from error

    def _get_idle_time(self, session: XorgSession) -> float:
        env = copy.deepcopy(os.environ)
        env["DISPLAY"] = ":{}".format(session.display)
        env["XAUTHORITY"] = str(Path("~" + session.user).expanduser() / ".Xauthority")

        try:
            idle_time_output = subprocess.check_output(  # noqa: S603, S607
                ["sudo", "-u", session.user, "xprintidle"], env=env
            )
            return float(idle_time_output.strip()) / 1000.0
        except FileNotFoundError as error:
            raise SevereCheckError("sudo executable not found") from error
        except (subprocess.CalledProcessError, ValueError) as error:
            self.logger.warning(
                "Unable to determine the idle time for display %s.",
                session.display,
                exc_info=True,
            )
            raise TemporaryCheckError("Unable to call xprintidle") from error

    def check(self) -> Optional[str]:
        for session in self._safe_provide_sessions():
            self.logger.info("Checking session %s", session)

            # check whether this users should be ignored completely
            if self._ignore_users_re.match(session.user) is not None:
                self.logger.debug("Skipping user '%s' due to request", session.user)
                continue

            # check whether any of the running processes of this user matches
            # the ignore regular expression. In that case we skip idletime
            # checking because we assume the user has a process running that
            # inevitably tampers with the idle time.
            if self._is_skip_process_running(session.user):
                continue

            idle_time = self._get_idle_time(session)
            self.logger.debug(
                "Idle time for display %s of user %s is %s seconds.",
                session.display,
                session.user,
                idle_time,
            )

            if idle_time < self._timeout:
                return (
                    "X session {} of user {} "
                    "has idle time {} < threshold {}".format(
                        session.display, session.user, idle_time, self._timeout
                    )
                )

        return None


class JsonPath(NetworkMixin, Activity):
    """Requests a URL and evaluates whether a JSONPath expression matches."""

    @classmethod
    def collect_init_args(cls, config: configparser.SectionProxy) -> Dict[str, Any]:
        from jsonpath_ng.ext import parse

        try:
            args = NetworkMixin.collect_init_args(config)
            args["jsonpath"] = parse(config["jsonpath"])
            return args
        except KeyError as error:
            raise ConfigurationError("Property jsonpath is missing") from error
        except Exception as error:
            raise ConfigurationError(f"JSONPath error {str(error)}") from error

    def __init__(self, name: str, jsonpath: "JSONPath", **kwargs: Any) -> None:
        Activity.__init__(self, name)
        NetworkMixin.__init__(self, accept="application/json", **kwargs)
        self._jsonpath = jsonpath

    def check(self) -> Optional[str]:
        import requests
        import requests.exceptions

        try:
            reply = self.request().json()
            matched = self._jsonpath.find(reply)
            if matched:
                # shorten to avoid excessive logging output
                return f"JSONPath {self._jsonpath} found elements " + shorten(
                    str(matched), 24
                )
            return None
        except (json.JSONDecodeError, requests.exceptions.RequestException) as error:
            raise TemporaryCheckError(error) from error


class LastLogActivity(Activity):
    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "LastLogActivity":
        import pytz

        try:
            return cls(
                name,
                Path(config["log_file"]),
                re.compile(config["pattern"]),
                timedelta(minutes=config.getint("minutes", fallback=10)),
                config.get("encoding", "ascii"),
                pytz.timezone(config.get("timezone", "UTC")),  # type: ignore
            )
        except KeyError as error:
            raise ConfigurationError(
                "Missing config key {}".format(error),
            ) from error
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
        log_file: Path,
        pattern: Pattern,
        delta: timedelta,
        encoding: str,
        default_timezone: timezone,
    ) -> None:
        if delta.total_seconds() < 0:
            raise ValueError("Given delta must be positive")
        if pattern.groups != 1:
            raise ValueError("Given pattern must have exactly one capture group")
        super().__init__(name=name)
        self.log_file = log_file
        self.pattern = pattern
        self.delta = delta
        self.encoding = encoding
        self.default_timezone = default_timezone

    def _safe_parse_date(self, match: str, now: datetime) -> datetime:
        from dateutil.parser import parse
        from dateutil.utils import default_tzinfo

        try:
            match_date = default_tzinfo(parse(match), self.default_timezone)
            if match_date > now:
                raise TemporaryCheckError(
                    "Detected date {} is in the future".format(match_date)
                )
            return match_date
        except ValueError as error:
            raise TemporaryCheckError(
                "Detected date {} cannot be parsed as a date".format(match)
            ) from error
        except OverflowError as error:
            raise TemporaryCheckError(
                "Detected date {} is out of the valid range".format(match)
            ) from error

    def _file_lines_reversed(self) -> Iterable[str]:
        try:
            # Probably not the most effective solution for large log files. Might need
            # optimizations later on.
            return reversed(
                self.log_file.read_text(encoding=self.encoding).splitlines()
            )
        except IOError as error:
            raise TemporaryCheckError(
                "Cannot access log file {}".format(self.log_file)
            ) from error

    def check(self) -> Optional[str]:
        lines = self._file_lines_reversed()

        now = datetime.now(tz=timezone.utc)
        for line in lines:
            match = self.pattern.match(line)
            if not match:
                continue

            match_date = self._safe_parse_date(match.group(1), now)

            # Only check the first line (reverse order) that has a match, not all
            if (now - match_date) < self.delta:
                return "Log activity in {} at {}".format(self.log_file, match_date)
            else:
                return None

        # No line matched at all
        return None
