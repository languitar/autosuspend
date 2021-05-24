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


def test_next_timer_executions() -> None:
    pytest.importorskip("dbus")
    pytest.importorskip("gi")
    # no working dbus mock interface exists for list units. Therefore, this is not easy
    # to test.
    assert next_timer_executions() is not None
