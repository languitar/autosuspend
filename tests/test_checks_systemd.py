import re
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from dbus.proxies import ProxyObject
from pytest_mock import MockerFixture

from autosuspend.checks import Check, ConfigurationError, TemporaryCheckError
from autosuspend.checks.systemd import (
    LogindSessionsIdle,
    SystemdScheduledShutdown,
    SystemdTimer,
    next_timer_executions,
)
from autosuspend.util.systemd import LogindDBusException

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
        now = datetime.now(UTC)

        assert SystemdTimer("foo", re.compile(".*")).check(now) is None

    def test_ignores_non_matching_timers(self, next_timer_executions: Mock) -> None:
        now = datetime.now(UTC)
        next_timer_executions.return_value = {"ignored": now}

        assert SystemdTimer("foo", re.compile("needle")).check(now) is None

    def test_finds_matching_timers(self, next_timer_executions: Mock) -> None:
        pattern = "foo"
        now = datetime.now(UTC)
        next_timer_executions.return_value = {pattern: now}

        assert SystemdTimer("foo", re.compile(pattern)).check(now) is now

    def test_selects_the_closest_execution_if_multiple_match(
        self, next_timer_executions: Mock
    ) -> None:
        now = datetime.now(UTC)
        next_timer_executions.return_value = {
            "later": now + timedelta(minutes=1),
            "matching": now,
        }

        assert SystemdTimer("foo", re.compile(".*")).check(now) is now


class TestSystemdScheduledShutdown(CheckTest):
    def create_instance(self, name: str) -> Check:
        return SystemdScheduledShutdown(name, 180)

    def test_create_default(self) -> None:
        check = SystemdScheduledShutdown.create("name", config_section())
        assert check._delta == 180

    def test_create_custom_delta(self) -> None:
        check = SystemdScheduledShutdown.create(
            "name", config_section({"delta": "300"})
        )
        assert check._delta == 300

    def test_create_invalid_delta(self) -> None:
        with pytest.raises(ConfigurationError):
            SystemdScheduledShutdown.create(
                "name", config_section({"delta": "not-a-number"})
            )

    def test_nothing_scheduled(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "autosuspend.checks.systemd.get_scheduled_shutdown",
            return_value=("", 0),
        )
        assert SystemdScheduledShutdown("name", 180).check(datetime.now(UTC)) is None

    @pytest.mark.parametrize("shutdown_type", ["reboot", "poweroff", "halt", "kexec"])
    def test_shutdown_scheduled(
        self, mocker: MockerFixture, shutdown_type: str
    ) -> None:
        scheduled = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        mocker.patch(
            "autosuspend.checks.systemd.get_scheduled_shutdown",
            return_value=(shutdown_type, int(scheduled.timestamp() * 1_000_000)),
        )
        result = SystemdScheduledShutdown("name", 180).check(datetime.now(UTC))
        assert result == scheduled - timedelta(seconds=180)

    @pytest.mark.parametrize("shutdown_type", ["dry-reboot", "dry-poweroff"])
    def test_dry_run_ignored(self, mocker: MockerFixture, shutdown_type: str) -> None:
        scheduled = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        mocker.patch(
            "autosuspend.checks.systemd.get_scheduled_shutdown",
            return_value=(shutdown_type, int(scheduled.timestamp() * 1_000_000)),
        )
        assert SystemdScheduledShutdown("name", 180).check(datetime.now(UTC)) is None

    def test_dbus_error_becomes_temporary_check_error(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "autosuspend.checks.systemd.get_scheduled_shutdown",
            side_effect=LogindDBusException("test"),
        )
        with pytest.raises(TemporaryCheckError):
            SystemdScheduledShutdown("name", 180).check(datetime.now(UTC))


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
