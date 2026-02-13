import pytest
from dbus.proxies import ProxyObject

from autosuspend.util.systemd import (
    LogindDBusException,
    has_inhibit_lock,
    list_logind_sessions,
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


class TestHasInhibitLock:
    @pytest.mark.usefixtures("logind")
    def test_no_inhibitors(self) -> None:
        assert has_inhibit_lock() is False

    def test_sleep_block(self, logind: ProxyObject) -> None:
        logind.AddInhibitor("sleep", "TestApp", "Testing", "block", 1000, 12345)
        assert has_inhibit_lock() is True

    def test_shutdown_block(self, logind: ProxyObject) -> None:
        logind.AddInhibitor("shutdown", "TestApp", "Testing", "block", 1000, 12345)
        assert has_inhibit_lock() is True

    def test_idle_block(self, logind: ProxyObject) -> None:
        logind.AddInhibitor("idle", "TestApp", "Testing", "block", 1000, 12345)
        assert has_inhibit_lock() is True

    def test_sleep_delay(self, logind: ProxyObject) -> None:
        # "delay" mode should not block
        logind.AddInhibitor("sleep", "TestApp", "Testing", "delay", 1000, 12345)
        assert has_inhibit_lock() is False

    def test_other_block(self, logind: ProxyObject) -> None:
        # Other inhibit types should not block
        logind.AddInhibitor(
            "handle-power-key", "TestApp", "Testing", "block", 1000, 12345
        )
        assert has_inhibit_lock() is False

    def test_multiple_inhibitors(self, logind: ProxyObject) -> None:
        logind.AddInhibitor("handle-power-key", "App1", "Testing", "block", 1000, 12345)
        logind.AddInhibitor("sleep", "App2", "Testing", "delay", 1000, 12346)
        assert has_inhibit_lock() is False

        logind.AddInhibitor("sleep", "App3", "Testing", "block", 1000, 12347)
        assert has_inhibit_lock() is True

    @pytest.mark.usefixtures("_logind_dbus_error")
    def test_dbus_error(self) -> None:
        with pytest.raises(LogindDBusException):
            has_inhibit_lock()
