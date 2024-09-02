from datetime import datetime, timedelta, timezone
import re
from unittest.mock import Mock

from dbus.proxies import ProxyObject
import pytest
from pytest_mock import MockerFixture

from autosuspend.checks import Check, ConfigurationError, TemporaryCheckError
from autosuspend.checks.systemd import (
    LogindSessionsIdle,
    next_timer_executions,
    SystemdTimer,
)

from . import CheckTest
from .utils import config_section


@pytest.mark.skip(reason="No dbusmock implementation available")
def test_next_timer_executions() -> None:
    assert next_timer_executions() is not None


class TestSystemdTimer(CheckTest):
    @staticmethod
    @pytest.fixture
    def next_timer_executions(mocker: MockerFixture) -> Mock:
        return mocker.patch("autosuspend.checks.systemd.next_timer_executions")

    def create_instance(self, name: str) -> Check:
        return SystemdTimer(name, re.compile(".*"))

    def test_create_handles_incorrect_expressions(self) -> None:
        with pytest.raises(ConfigurationError):
            SystemdTimer.create("somename", config_section({"match": "(.*"}))

    def test_create_raises_if_match_is_missing(self) -> None:
        with pytest.raises(ConfigurationError):
            SystemdTimer.create("somename", config_section())

    def test_works_without_timers(self, next_timer_executions: Mock) -> None:
        next_timer_executions.return_value = {}
        now = datetime.now(timezone.utc)

        assert SystemdTimer("foo", re.compile(".*")).check(now) is None

    def test_ignores_non_matching_timers(self, next_timer_executions: Mock) -> None:
        now = datetime.now(timezone.utc)
        next_timer_executions.return_value = {"ignored": now}

        assert SystemdTimer("foo", re.compile("needle")).check(now) is None

    def test_finds_matching_timers(self, next_timer_executions: Mock) -> None:
        pattern = "foo"
        now = datetime.now(timezone.utc)
        next_timer_executions.return_value = {pattern: now}

        assert SystemdTimer("foo", re.compile(pattern)).check(now) is now

    def test_selects_the_closest_execution_if_multiple_match(
        self, next_timer_executions: Mock
    ) -> None:
        now = datetime.now(timezone.utc)
        next_timer_executions.return_value = {
            "later": now + timedelta(minutes=1),
            "matching": now,
        }

        assert SystemdTimer("foo", re.compile(".*")).check(now) is now


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

    def test_ignore_unknown_class(self, logind: ProxyObject) -> None:
        logind.AddSession("c1", "seat0", 1042, "user", True)

        check = LogindSessionsIdle(
            "test", ["test"], ["active", "online"], ["nosuchclass"]
        )
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

    def test_configure_classes(self) -> None:
        check = LogindSessionsIdle.create(
            "name", config_section({"classes": "test, bla,foo"})
        )
        assert check._classes == ["test", "bla", "foo"]

    @pytest.mark.usefixtures("_logind_dbus_error")
    def test_dbus_error(self) -> None:
        check = LogindSessionsIdle("test", ["test"], ["active", "online"])

        with pytest.raises(TemporaryCheckError):
            check.check()
