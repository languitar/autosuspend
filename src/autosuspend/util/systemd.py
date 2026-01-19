from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import dbus


def _get_bus() -> "dbus.SystemBus":
    import dbus

    return dbus.SystemBus()


class LogindDBusException(RuntimeError):
    """Indicates an error communicating to Logind via DBus."""


def list_logind_sessions() -> Iterable[tuple[str, dict]]:
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
