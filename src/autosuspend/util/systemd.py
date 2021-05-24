from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Tuple, TYPE_CHECKING


if TYPE_CHECKING:
    import dbus


def _get_bus() -> "dbus.SystemBus":
    import dbus

    return dbus.SystemBus()


class LogindDBusException(RuntimeError):
    """Indicates an error communicating to Logind via DBus."""


def list_logind_sessions() -> Iterable[Tuple[str, dict]]:
    """List running logind sessions and their properties.

    Returns:
        list of (session_id, properties dict):
            A list with tuples of sessions ids and their associated properties
            represented as dicts.
    """
    import dbus

    try:
        bus = _get_bus()
        login1 = bus.get_object("org.freedesktop.login1", "/org/freedesktop/login1")

        sessions = login1.ListSessions(dbus_interface="org.freedesktop.login1.Manager")

        results = []
        for session_id, path in [(s[0], s[4]) for s in sessions]:
            session = bus.get_object("org.freedesktop.login1", path)
            properties_interface = dbus.Interface(
                session, "org.freedesktop.DBus.Properties"
            )
            properties = properties_interface.GetAll("org.freedesktop.login1.Session")
            results.append((session_id, properties))
    except dbus.exceptions.DBusException as error:
        raise LogindDBusException(error) from error

    return results


def next_timer_executions() -> Dict[str, datetime]:
    import dbus

    bus = _get_bus()

    systemd = bus.get_object("org.freedesktop.systemd1", "/org/freedesktop/systemd1")
    units = systemd.ListUnits(dbus_interface="org.freedesktop.systemd1.Manager")
    timers = [unit for unit in units if unit[0].endswith(".timer")]

    result: Dict[str, datetime] = {}
    for timer in timers:
        obj = bus.get_object("org.freedesktop.systemd1", timer[6])
        properties_interface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        props = properties_interface.GetAll("org.freedesktop.systemd1.Timer")

        next_time: Optional[datetime] = None
        if props["NextElapseUSecRealtime"]:
            next_time = datetime.fromtimestamp(
                props["NextElapseUSecRealtime"] / 1000000,
                tz=timezone.utc,
            )
        elif props["NextElapseUSecMonotonic"]:
            next_time = datetime.now(tz=timezone.utc) + timedelta(
                seconds=props["NextElapseUSecMonotonic"] / 1000000
            )

        if next_time:
            result[str(timer[0])] = next_time

    return result
