from datetime import UTC, datetime, timedelta

import pytest

from autosuspend.checks import Check, ConfigurationError
from autosuspend.checks.stub import Periodic

from . import CheckTest
from .utils import config_section


class TestPeriodic(CheckTest):
    def create_instance(self, name: str) -> Check:
        delta = timedelta(seconds=10, minutes=42)
        return Periodic(name, delta)

    def test_create(self) -> None:
        check = Periodic.create(
            "name", config_section({"unit": "seconds", "value": "13"})
        )
        assert check._delta == timedelta(seconds=13)

    def test_create_wrong_unit(self) -> None:
        with pytest.raises(ConfigurationError):
            Periodic.create("name", config_section({"unit": "asdfasdf", "value": "13"}))

    def test_create_not_numeric(self) -> None:
        with pytest.raises(ConfigurationError):
            Periodic.create(
                "name", config_section({"unit": "seconds", "value": "asdfasd"})
            )

    def test_create_no_unit(self) -> None:
        with pytest.raises(ConfigurationError):
            Periodic.create("name", config_section({"value": "13"}))

    def test_create_float(self) -> None:
        Periodic.create(
            "name", config_section({"unit": "seconds", "value": "21312.12"})
        )

    def test_check(self) -> None:
        delta = timedelta(seconds=10, minutes=42)
        check = Periodic("test", delta)
        now = datetime.now(UTC)
        assert check.check(now) == now + delta
