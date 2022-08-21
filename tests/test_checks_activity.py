from dbus.proxies import ProxyObject
import pytest

from autosuspend.checks import Check, TemporaryCheckError
from autosuspend.checks.activity import LogindSessionsIdle

from . import CheckTest
from tests.utils import config_section


class TestLogindSessionsIdle(CheckTest):
    def create_instance(self, name: str) -> Check:
        return LogindSessionsIdle(name, ["tty", "x11", "wayland"], ["active", "online"])

    def test_active(self, logind: ProxyObject) -> None:
        logind.AddSession("c1", "seat0", 1042, "auser", True)

        check = LogindSessionsIdle("test", ["test"], ["active", "online"])
        assert check.check() is not None

    @pytest.mark.skip(reason="No known way to set idle hint in dbus mock right now")
    def test_inactive(self, logind: ProxyObject) -> None:
        logind.AddSession("c1", "seat0", 1042, "auser", False)

        check = LogindSessionsIdle("test", ["test"], ["active", "online"])
        assert check.check() is None

    def test_ignore_unknow_type(self, logind: ProxyObject) -> None:
        logind.AddSession("c1", "seat0", 1042, "auser", True)

        check = LogindSessionsIdle("test", ["not_test"], ["active", "online"])
        assert check.check() is None

    def test_configure_defaults(self) -> None:
        check = LogindSessionsIdle.create("name", config_section())
        assert check._types == ["tty", "x11", "wayland"]
        assert check._states == ["active", "online"]

    def test_configure_types(self) -> None:
        check = LogindSessionsIdle.create(
            "name", config_section({"types": "test, bla,foo"})
        )
        assert check._types == ["test", "bla", "foo"]

    def test_configure_states(self) -> None:
        check = LogindSessionsIdle.create(
            "name", config_section({"states": "test, bla,foo"})
        )
        assert check._states == ["test", "bla", "foo"]

    @pytest.mark.usefixtures("_logind_dbus_error")
    def test_dbus_error(self) -> None:
        check = LogindSessionsIdle("test", ["test"], ["active", "online"])

        with pytest.raises(TemporaryCheckError):
            check.check()
