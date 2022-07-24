from dbus.proxies import ProxyObject
import pytest

from autosuspend.util.systemd import (
    list_logind_sessions,
    LogindDBusException,
    next_timer_executions,
)


def test_list_logind_sessions_empty(logind: ProxyObject) -> None:
    assert len(list(list_logind_sessions())) == 0

    logind.AddSession("c1", "seat0", 1042, "auser", True)
    sessions = list(list_logind_sessions())
    assert len(sessions) == 1
    assert sessions[0][0] == "c1"


@pytest.mark.usefixtures("_logind_dbus_error")
def test_list_logind_sessions_dbus_error() -> None:
    with pytest.raises(LogindDBusException):
        list_logind_sessions()


@pytest.mark.skip(reason="No dbusmock implementation available")
def test_next_timer_executions() -> None:
    assert next_timer_executions() is not None
