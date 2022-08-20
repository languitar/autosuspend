"""Contains checks directly using the Linux operating system concepts."""


import configparser
from contextlib import suppress
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from typing import Iterable, List, Optional, Pattern, Tuple
import warnings

import psutil

from . import (
    Activity,
    ConfigurationError,
    SevereCheckError,
    TemporaryCheckError,
    Wakeup,
)
from .util import CommandMixin
from ..util.subprocess import raise_severe_if_command_not_found


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
        Activity.__init__(self, name)

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
        Activity.__init__(self, name)
        self._threshold = threshold

    def check(self) -> Optional[str]:
        loadcurrent = os.getloadavg()[1]
        self.logger.debug("Load: %s", loadcurrent)
        if loadcurrent > self._threshold:
            return "Load {} > threshold {}".format(loadcurrent, self._threshold)
        else:
            return None


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
        Activity.__init__(self, name)
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
        Activity.__init__(self, name)
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
                    self.logger.debug("host %s appears to be up", host)
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
        Activity.__init__(self, name)
        self._processes = processes

    def check(self) -> Optional[str]:
        for proc in psutil.process_iter():
            with suppress(psutil.NoSuchProcess):
                pinfo = proc.name()
                if pinfo in self._processes:
                    return "Process {} is running".format(pinfo)
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


class File(Wakeup):
    """Determines scheduled wake ups from the contents of a file on disk.

    File contents are interpreted as a Unix timestamp in seconds UTC.
    """

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "File":
        try:
            path = Path(config["path"])
            return cls(name, path)
        except KeyError as error:
            raise ConfigurationError("Missing option path") from error

    def __init__(self, name: str, path: Path) -> None:
        Wakeup.__init__(self, name)
        self._path = path

    def check(self, timestamp: datetime) -> Optional[datetime]:
        try:
            first_line = self._path.read_text().splitlines()[0]
            return datetime.fromtimestamp(float(first_line.strip()), timezone.utc)
        except FileNotFoundError:
            # this is ok
            return None
        except (ValueError, IOError) as error:
            raise TemporaryCheckError(
                "Next wakeup time cannot be read despite a file being present"
            ) from error


class Command(CommandMixin, Wakeup):
    """Determine wake up times based on an external command.

    The called command must return a timestamp in UTC or nothing in case no
    wake up is planned.
    """

    def __init__(self, name: str, command: str) -> None:
        CommandMixin.__init__(self, command)
        Wakeup.__init__(self, name)

    def check(self, timestamp: datetime) -> Optional[datetime]:
        try:
            output = subprocess.check_output(
                self._command,
                shell=True,  # noqa: S602
            ).splitlines()[0]
            self.logger.debug(
                "Command %s succeeded with output %s", self._command, output
            )
            if output.strip():
                return datetime.fromtimestamp(float(output.strip()), timezone.utc)
            else:
                return None

        except subprocess.CalledProcessError as error:
            raise_severe_if_command_not_found(error)
            raise TemporaryCheckError(
                "Unable to call the configured command"
            ) from error
        except ValueError as error:
            raise TemporaryCheckError(
                "Return value cannot be interpreted as a timestamp"
            ) from error
