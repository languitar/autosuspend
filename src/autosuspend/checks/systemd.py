import configparser
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, Iterable, Optional, Pattern, Tuple

import dbus

from . import Activity, ConfigurationError, TemporaryCheckError, Wakeup
from ..util.systemd import list_logind_sessions, LogindDBusException


_UINT64_MAX = 18446744073709551615


def next_timer_executions() -> Dict[str, datetime]:
    bus = dbus.SystemBus()

    systemd = bus.get_object("org.freedesktop.systemd1", "/org/freedesktop/systemd1")
    units = systemd.ListUnits(dbus_interface="org.freedesktop.systemd1.Manager")
    timers = [unit for unit in units if unit[0].endswith(".timer")]

    def get_if_set(props: Dict[str, Any], key: str) -> Optional[int]:
        # For timers running after boot, next execution time might not be available. In
        # this case, the expected keys are all set to uint64 max.
        if props[key] and props[key] != _UINT64_MAX:
            return props[key]
        else:
            return None

    result: Dict[str, datetime] = {}
    for timer in timers:
        obj = bus.get_object("org.freedesktop.systemd1", timer[6])
        properties_interface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        props = properties_interface.GetAll("org.freedesktop.systemd1.Timer")

        realtime = get_if_set(props, "NextElapseUSecRealtime")
        monotonic = get_if_set(props, "NextElapseUSecMonotonic")
        next_time: Optional[datetime] = None
        if realtime is not None:
            next_time = datetime.fromtimestamp(
                realtime / 1000000,
                tz=timezone.utc,
            )
        elif monotonic is not None:
            next_time = datetime.now(tz=timezone.utc) + timedelta(
                seconds=monotonic / 1000000
            )

        if next_time:
            result[str(timer[0])] = next_time

    return result


class SystemdTimer(Wakeup):
    """Ensures that the system is active when some selected SystemD timers will run."""

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "SystemdTimer":
        try:
            return cls(name, re.compile(config["match"]))
        except (re.error, ValueError, KeyError, TypeError) as error:
            raise ConfigurationError(str(error)) from error

    def __init__(self, name: str, match: Pattern) -> None:
        Wakeup.__init__(self, name)
        self._match = match

    def check(self, timestamp: datetime) -> Optional[datetime]:  # noqa: ARG002
        executions = next_timer_executions()
        matching_executions = [
            next_run for name, next_run in executions.items() if self._match.match(name)
        ]
        try:
            return min(matching_executions)
        except ValueError:
            return None


class LogindSessionsIdle(Activity):
    """Prevents suspending in case a logind session is marked not idle.

    The decision is based on the ``IdleHint`` property of logind sessions.
    """

    @classmethod
    def create(
        cls,
        name: str,
        config: configparser.SectionProxy,
    ) -> "LogindSessionsIdle":
        types = config.get("types", fallback="tty,x11,wayland").split(",")
        types = [t.strip() for t in types]
        states = config.get("states", fallback="active,online").split(",")
        states = [t.strip() for t in states]
        classes = config.get("classes", fallback="user").split(",")
        classes = [t.strip() for t in classes]
        return cls(name, types, states, classes)

    def __init__(
        self,
        name: str,
        types: Iterable[str],
        states: Iterable[str],
        classes: Iterable[str] = ("user"),
    ) -> None:
        Activity.__init__(self, name)
        self._types = types
        self._states = states
        self._classes = classes

    @staticmethod
    def _list_logind_sessions() -> Iterable[Tuple[str, dict]]:
        try:
            return list_logind_sessions()
        except LogindDBusException as error:
            raise TemporaryCheckError(error) from error

    def check(self) -> Optional[str]:
        for session_id, properties in self._list_logind_sessions():
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
            if properties["Class"] not in self._classes:
                self.logger.debug(
                    "Ignoring session because its class is %s", properties["Class"]
                )
                continue

            if not properties["IdleHint"]:
                return f"Login session {session_id} is not idle"

        return None
