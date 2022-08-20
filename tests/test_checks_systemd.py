from datetime import datetime, timedelta, timezone
import re
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from autosuspend.checks import Check, ConfigurationError
from autosuspend.checks.systemd import next_timer_executions, SystemdTimer

from . import CheckTest
from .utils import config_section


@pytest.mark.skip(reason="No dbusmock implementation available")
def test_next_timer_executions() -> None:
    assert next_timer_executions() is not None


class TestSystemdTimer(CheckTest):
    @staticmethod
    @pytest.fixture()
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
