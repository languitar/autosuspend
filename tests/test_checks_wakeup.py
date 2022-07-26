from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import subprocess
from unittest.mock import Mock

import pytest
from pytest_mock import MockFixture

from autosuspend.checks import (
    Check,
    ConfigurationError,
    SevereCheckError,
    TemporaryCheckError,
)
from autosuspend.checks.wakeup import Command, File, Periodic, SystemdTimer

from . import CheckTest
from .utils import config_section


class TestFile(CheckTest):
    def create_instance(self, name: str) -> Check:
        return File(name, Path("asdf"))

    def test_create(self) -> None:
        check = File.create("name", config_section({"path": "/tmp/test"}))
        assert check._path == Path("/tmp/test")

    def test_create_no_path(self) -> None:
        with pytest.raises(ConfigurationError):
            File.create("name", config_section())

    def test_smoke(self, tmp_path: Path) -> None:
        test_file = tmp_path / "file"
        test_file.write_text("42\n\n")
        assert File("name", test_file).check(
            datetime.now(timezone.utc)
        ) == datetime.fromtimestamp(42, timezone.utc)

    def test_no_file(self, tmp_path: Path) -> None:
        assert File("name", tmp_path / "narf").check(datetime.now(timezone.utc)) is None

    def test_handle_permission_error(self, tmp_path: Path) -> None:
        file_path = tmp_path / "test"
        file_path.write_bytes(b"2314898")
        file_path.chmod(0)
        with pytest.raises(TemporaryCheckError):
            File("name", file_path).check(datetime.now(timezone.utc))

    def test_handle_io_error(self, tmp_path: Path, mocker: MockFixture) -> None:
        file_path = tmp_path / "test"
        file_path.write_bytes(b"2314898")
        mocker.patch("pathlib.Path.read_text").side_effect = IOError
        with pytest.raises(TemporaryCheckError):
            File("name", file_path).check(datetime.now(timezone.utc))

    def test_invalid_number(self, tmp_path: Path) -> None:
        test_file = tmp_path / "filexxx"
        test_file.write_text("nonumber\n\n")
        with pytest.raises(TemporaryCheckError):
            File("name", test_file).check(datetime.now(timezone.utc))


class TestCommand(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Command(name, "asdf")

    def test_smoke(self) -> None:
        check = Command("test", "echo 1234")
        assert check.check(datetime.now(timezone.utc)) == datetime.fromtimestamp(
            1234, timezone.utc
        )

    def test_no_output(self) -> None:
        check = Command("test", "echo")
        assert check.check(datetime.now(timezone.utc)) is None

    def test_not_parseable(self) -> None:
        check = Command("test", "echo asdfasdf")
        with pytest.raises(TemporaryCheckError):
            check.check(datetime.now(timezone.utc))

    def test_multiple_lines(self, mocker: MockFixture) -> None:
        mock = mocker.patch("subprocess.check_output")
        mock.return_value = "1234\nignore\n"
        check = Command("test", "echo bla")
        assert check.check(datetime.now(timezone.utc)) == datetime.fromtimestamp(
            1234, timezone.utc
        )

    def test_multiple_lines_but_empty(self, mocker: MockFixture) -> None:
        mock = mocker.patch("subprocess.check_output")
        mock.return_value = "   \nignore\n"
        check = Command("test", "echo bla")
        assert check.check(datetime.now(timezone.utc)) is None

    def test_process_error(self, mocker: MockFixture) -> None:
        mock = mocker.patch("subprocess.check_output")
        mock.side_effect = subprocess.CalledProcessError(2, "foo bar")
        check = Command("test", "echo bla")
        with pytest.raises(TemporaryCheckError):
            check.check(datetime.now(timezone.utc))

    def test_missing_executable(self, mocker: MockFixture) -> None:
        check = Command("test", "reallydoesntexist bla")
        with pytest.raises(SevereCheckError):
            check.check(datetime.now(timezone.utc))


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
        now = datetime.now(timezone.utc)
        assert check.check(now) == now + delta


class TestSystemdTimer(CheckTest):
    @staticmethod
    @pytest.fixture()
    def next_timer_executions(mocker: MockFixture) -> Mock:
        return mocker.patch("autosuspend.checks.wakeup.next_timer_executions")

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
