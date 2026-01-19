import pytest
from dbus.proxies import ProxyObject

from autosuspend.util.systemd import LogindDBusException, list_logind_sessions


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
