from collections.abc import Iterable

import dbus


def _get_bus() -> dbus.SystemBus:
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


def has_inhibit_lock() -> bool:
    """Check if there are any blocking inhibit locks that prevent sleep.

    Returns:
        True if there are inhibit locks blocking sleep/shutdown/idle, False otherwise.

    Raises:
        LogindDBusException: If communication with logind fails.
    """
    try:
        bus = _get_bus()
        login1 = bus.get_object("org.freedesktop.login1", "/org/freedesktop/login1")

        inhibitors = login1.ListInhibitors(
            dbus_interface="org.freedesktop.login1.Manager"
        )

        # Check for blocking inhibit locks on sleep, shutdown, or idle
        for inhibitor in inhibitors:
            what, _who, _why, mode, _uid, _pid = inhibitor
            if mode == "block" and any(
                lock in what for lock in ["sleep", "shutdown", "idle"]
            ):
                return True

        return False
    except dbus.exceptions.DBusException as error:
        raise LogindDBusException(error) from error
