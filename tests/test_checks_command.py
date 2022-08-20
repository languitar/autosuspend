from datetime import datetime, timezone
import subprocess
from typing import Optional

import pytest
from pytest_mock import MockerFixture

from autosuspend.checks import (
    Activity,
    Check,
    ConfigurationError,
    SevereCheckError,
    TemporaryCheckError,
)
from autosuspend.checks.command import CommandActivity, CommandMixin, CommandWakeup

from . import CheckTest
from .utils import config_section


class _CommandMixinSub(CommandMixin, Activity):
    def __init__(self, name: str, command: str) -> None:
        Activity.__init__(self, name)
        CommandMixin.__init__(self, command)

    def check(self) -> Optional[str]:
        pass


class TestCommandMixin:
    def test_create(self) -> None:
        section = config_section({"command": "narf bla"})
        check: _CommandMixinSub = _CommandMixinSub.create(
            "name",
            section,
        )  # type: ignore
        assert check._command == "narf bla"

    def test_create_no_command(self) -> None:
        with pytest.raises(ConfigurationError):
            _CommandMixinSub.create("name", config_section())


class TestCommandActivity(CheckTest):
    def create_instance(self, name: str) -> Check:
        return CommandActivity(name, "asdfasdf")

    def test_check(self, mocker: MockerFixture) -> None:
        mock = mocker.patch("subprocess.check_call")
        assert (
            CommandActivity.create(
                "name", config_section({"command": "foo bar"})
            ).check()  # type: ignore
            is not None
        )
        mock.assert_called_once_with("foo bar", shell=True)

    def test_check_no_match(self, mocker: MockerFixture) -> None:
        mock = mocker.patch("subprocess.check_call")
        mock.side_effect = subprocess.CalledProcessError(2, "foo bar")
        assert (
            CommandActivity.create("name", config_section({"command": "foo bar"})).check() is None  # type: ignore
        )
        mock.assert_called_once_with("foo bar", shell=True)

    def test_command_not_found(self) -> None:
        with pytest.raises(SevereCheckError):
            CommandActivity.create(
                "name", config_section({"command": "thisreallydoesnotexist"})
            ).check()  # type: ignore


class TestCommandWakeup(CheckTest):
    def create_instance(self, name: str) -> Check:
        return CommandWakeup(name, "asdf")

    def test_smoke(self) -> None:
        check = CommandWakeup("test", "echo 1234")
        assert check.check(datetime.now(timezone.utc)) == datetime.fromtimestamp(
            1234, timezone.utc
        )

    def test_no_output(self) -> None:
        check = CommandWakeup("test", "echo")
        assert check.check(datetime.now(timezone.utc)) is None

    def test_not_parseable(self) -> None:
        check = CommandWakeup("test", "echo asdfasdf")
        with pytest.raises(TemporaryCheckError):
            check.check(datetime.now(timezone.utc))

    def test_multiple_lines(self, mocker: MockerFixture) -> None:
        mock = mocker.patch("subprocess.check_output")
        mock.return_value = "1234\nignore\n"
        check = CommandWakeup("test", "echo bla")
        assert check.check(datetime.now(timezone.utc)) == datetime.fromtimestamp(
            1234, timezone.utc
        )

    def test_multiple_lines_but_empty(self, mocker: MockerFixture) -> None:
        mock = mocker.patch("subprocess.check_output")
        mock.return_value = "   \nignore\n"
        check = CommandWakeup("test", "echo bla")
        assert check.check(datetime.now(timezone.utc)) is None

    def test_process_error(self, mocker: MockerFixture) -> None:
        mock = mocker.patch("subprocess.check_output")
        mock.side_effect = subprocess.CalledProcessError(2, "foo bar")
        check = CommandWakeup("test", "echo bla")
        with pytest.raises(TemporaryCheckError):
            check.check(datetime.now(timezone.utc))

    def test_missing_executable(self) -> None:
        check = CommandWakeup("test", "reallydoesntexist bla")
        with pytest.raises(SevereCheckError):
            check.check(datetime.now(timezone.utc))
