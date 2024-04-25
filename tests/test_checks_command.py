from datetime import datetime, timezone
import subprocess

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

    def check(self) -> str | None:
        pass


class TestCommandMixin:
    class TestCreate:
        def test_it_works(self) -> None:
            section = config_section({"command": "narf bla"})
            check: _CommandMixinSub = _CommandMixinSub.create(
                "name",
                section,
            )  # type: ignore
            assert check._command == "narf bla"

        def test_throws_if_no_command_is_configured(self) -> None:
            with pytest.raises(ConfigurationError):
                _CommandMixinSub.create("name", config_section())


class TestCommandActivity(CheckTest):
    def create_instance(self, name: str) -> Check:
        return CommandActivity(name, "asdfasdf")

    def test_reports_activity_if_the_command_succeeds(
        self, mocker: MockerFixture
    ) -> None:
        mock = mocker.patch("subprocess.check_call")
        assert (
            CommandActivity.create(
                "name", config_section({"command": "foo bar"})
            ).check()  # type: ignore
            is not None
        )
        mock.assert_called_once_with("foo bar", shell=True)

    def test_reports_no_activity_if_the_command_fails(
        self, mocker: MockerFixture
    ) -> None:
        mock = mocker.patch("subprocess.check_call")
        mock.side_effect = subprocess.CalledProcessError(2, "foo bar")
        assert (
            CommandActivity.create("name", config_section({"command": "foo bar"})).check() is None  # type: ignore
        )
        mock.assert_called_once_with("foo bar", shell=True)

    def test_reports_missing_commands(self) -> None:
        with pytest.raises(SevereCheckError):
            CommandActivity.create(
                "name", config_section({"command": "thisreallydoesnotexist"})
            ).check()  # type: ignore


class TestCommandWakeup(CheckTest):
    def create_instance(self, name: str) -> Check:
        return CommandWakeup(name, "asdf")

    def test_reports_the_wakup_time_received_from_the_command(self) -> None:
        check = CommandWakeup("test", "echo 1234")
        assert check.check(datetime.now(timezone.utc)) == datetime.fromtimestamp(
            1234, timezone.utc
        )

    def test_reports_no_wakeup_without_command_output(self) -> None:
        check = CommandWakeup("test", "echo")
        assert check.check(datetime.now(timezone.utc)) is None

    def test_raises_an_error_if_the_command_output_cannot_be_parsed(self) -> None:
        check = CommandWakeup("test", "echo asdfasdf")
        with pytest.raises(TemporaryCheckError):
            check.check(datetime.now(timezone.utc))

    def test_uses_only_the_first_output_line(self, mocker: MockerFixture) -> None:
        mock = mocker.patch("subprocess.check_output")
        mock.return_value = "1234\nignore\n"
        check = CommandWakeup("test", "echo bla")
        assert check.check(datetime.now(timezone.utc)) == datetime.fromtimestamp(
            1234, timezone.utc
        )

    def test_uses_only_the_first_line_even_if_empty(
        self, mocker: MockerFixture
    ) -> None:
        mock = mocker.patch("subprocess.check_output")
        mock.return_value = "   \nignore\n"
        check = CommandWakeup("test", "echo bla")
        assert check.check(datetime.now(timezone.utc)) is None

    def test_raises_if_the_called_command_fails(self, mocker: MockerFixture) -> None:
        mock = mocker.patch("subprocess.check_output")
        mock.side_effect = subprocess.CalledProcessError(2, "foo bar")
        check = CommandWakeup("test", "echo bla")
        with pytest.raises(TemporaryCheckError):
            check.check(datetime.now(timezone.utc))

    def test_reports_missing_executables(self) -> None:
        check = CommandWakeup("test", "reallydoesntexist bla")
        with pytest.raises(SevereCheckError):
            check.check(datetime.now(timezone.utc))
