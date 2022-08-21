from getpass import getuser
import logging
from pathlib import Path
import re
import subprocess
from typing import Any

import pytest
from pytest_mock import MockerFixture

from autosuspend.checks import (
    Check,
    ConfigurationError,
    SevereCheckError,
    TemporaryCheckError,
)
from autosuspend.checks.xorg import (
    list_sessions_logind,
    list_sessions_sockets,
    XIdleTime,
    XorgSession,
)
from autosuspend.util.systemd import LogindDBusException

from . import CheckTest
from .utils import config_section


class TestListSessionsSockets:
    def test_empty(self, tmp_path: Path) -> None:
        assert list_sessions_sockets(tmp_path) == []

    @pytest.mark.parametrize("number", [0, 10, 1024])
    def test_extracts_valid_sockets(self, tmp_path: Path, number: int) -> None:
        session_sock = tmp_path / f"X{number}"
        session_sock.touch()

        assert list_sessions_sockets(tmp_path) == [
            XorgSession(number, session_sock.owner())
        ]

    @pytest.mark.parametrize("invalid_number", ["", "string", "  "])
    def test_ignores_and_warns_on_invalid_numbers(
        self,
        tmp_path: Path,
        invalid_number: str,
        caplog: Any,
    ) -> None:
        (tmp_path / f"X{invalid_number}").touch()

        with caplog.at_level(logging.WARNING):
            assert list_sessions_sockets(tmp_path) == []
            assert caplog.records != []

    def test_ignores_and_warns_on_unknown_users(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        caplog: Any,
    ) -> None:
        (tmp_path / "X0").touch()
        mocker.patch("pathlib.Path.owner").side_effect = KeyError()

        with caplog.at_level(logging.WARNING):
            assert list_sessions_sockets(tmp_path) == []
            assert caplog.records != []

    def test_ignores_other_files(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "asdf").touch()

        assert list_sessions_sockets(tmp_path) == []

    def test_returns_multiple(self, tmp_path: Path) -> None:
        (tmp_path / "X0").touch()
        (tmp_path / "X1").touch()

        assert len(list_sessions_sockets(tmp_path)) == 2


_LIST_LOGIND_SESSIONS_TO_PATCH = "autosuspend.checks.xorg.list_logind_sessions"


class TestListSessionsLogind:
    def test_extracts_valid_sessions(self, mocker: MockerFixture) -> None:
        username = "test_user"
        display = 42
        mocker.patch(_LIST_LOGIND_SESSIONS_TO_PATCH).return_value = [
            ("id", {"Name": username, "Display": f":{display}"})
        ]

        assert list_sessions_logind() == [XorgSession(display, username)]

    def test_ignores_sessions_with_missing_properties(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch(_LIST_LOGIND_SESSIONS_TO_PATCH).return_value = [
            ("id", {"Name": "someuser"}),
            ("id", {"Display": ":42"}),
        ]

        assert list_sessions_logind() == []

    def test_ignores_and_warns_on_invalid_display_numbers(
        self,
        mocker: MockerFixture,
        caplog: Any,
    ) -> None:
        mocker.patch(_LIST_LOGIND_SESSIONS_TO_PATCH).return_value = [
            ("id", {"Name": "someuser", "Display": "XXX"}),
        ]

        with caplog.at_level(logging.WARNING):
            assert list_sessions_logind() == []
            assert caplog.records != []


class TestXIdleTime(CheckTest):
    def create_instance(self, name: str) -> Check:
        # concrete values are never used in the test
        return XIdleTime(name, 10, "sockets", None, None)  # type: ignore

    def test_smoke(self, mocker: MockerFixture) -> None:
        check = XIdleTime("name", 100, "logind", re.compile(r"a^"), re.compile(r"a^"))
        mocker.patch.object(check, "_provide_sessions").return_value = [
            XorgSession(42, getuser()),
        ]

        co_mock = mocker.patch("subprocess.check_output")
        co_mock.return_value = "123"

        res = check.check()
        assert res is not None
        assert " 0.123 " in res

        args, kwargs = co_mock.call_args
        assert getuser() in args[0]
        assert kwargs["env"]["DISPLAY"] == ":42"
        assert getuser() in kwargs["env"]["XAUTHORITY"]

    def test_no_activity(self, mocker: MockerFixture) -> None:
        check = XIdleTime("name", 100, "logind", re.compile(r"a^"), re.compile(r"a^"))
        mocker.patch.object(check, "_provide_sessions").return_value = [
            XorgSession(42, getuser()),
        ]

        mocker.patch("subprocess.check_output").return_value = "120000"

        assert check.check() is None

    def test_multiple_sessions(self, mocker: MockerFixture) -> None:
        check = XIdleTime("name", 100, "logind", re.compile(r"a^"), re.compile(r"a^"))
        mocker.patch.object(check, "_provide_sessions").return_value = [
            XorgSession(42, getuser()),
            XorgSession(17, "root"),
        ]

        co_mock = mocker.patch("subprocess.check_output")
        co_mock.side_effect = [
            "120000",
            "123",
        ]

        res = check.check()
        assert res is not None
        assert " 0.123 " in res

        assert co_mock.call_count == 2
        # check second call for correct values, not checked before
        args, kwargs = co_mock.call_args_list[1]
        assert "root" in args[0]
        assert kwargs["env"]["DISPLAY"] == ":17"
        assert "root" in kwargs["env"]["XAUTHORITY"]

    def test_handle_call_error(self, mocker: MockerFixture) -> None:
        check = XIdleTime("name", 100, "logind", re.compile(r"a^"), re.compile(r"a^"))
        mocker.patch.object(check, "_provide_sessions").return_value = [
            XorgSession(42, getuser()),
        ]

        mocker.patch(
            "subprocess.check_output",
        ).side_effect = subprocess.CalledProcessError(2, "foo")

        with pytest.raises(TemporaryCheckError):
            check.check()

    def test_create_default(self) -> None:
        check = XIdleTime.create("name", config_section())
        assert check._timeout == 600
        assert check._ignore_process_re == re.compile(r"a^")
        assert check._ignore_users_re == re.compile(r"a^")
        assert check._provide_sessions == list_sessions_sockets

    def test_create(self) -> None:
        check = XIdleTime.create(
            "name",
            config_section(
                {
                    "timeout": "42",
                    "ignore_if_process": ".*test",
                    "ignore_users": "test.*test",
                    "method": "logind",
                }
            ),
        )
        assert check._timeout == 42
        assert check._ignore_process_re == re.compile(r".*test")
        assert check._ignore_users_re == re.compile(r"test.*test")
        assert check._provide_sessions == list_sessions_logind

    def test_create_no_int(self) -> None:
        with pytest.raises(ConfigurationError):
            XIdleTime.create("name", config_section({"timeout": "string"}))

    def test_create_broken_process_re(self) -> None:
        with pytest.raises(ConfigurationError):
            XIdleTime.create("name", config_section({"ignore_if_process": "[[a-9]"}))

    def test_create_broken_users_re(self) -> None:
        with pytest.raises(ConfigurationError):
            XIdleTime.create("name", config_section({"ignore_users": "[[a-9]"}))

    def test_create_unknown_method(self) -> None:
        with pytest.raises(ConfigurationError):
            XIdleTime.create("name", config_section({"method": "asdfasdf"}))

    def test_list_sessions_logind_dbus_error(self, mocker: MockerFixture) -> None:
        check = XIdleTime.create("name", config_section())
        mocker.patch.object(
            check, "_provide_sessions"
        ).side_effect = LogindDBusException()

        with pytest.raises(TemporaryCheckError):
            check._safe_provide_sessions()

    def test_sudo_not_found(self, mocker: MockerFixture) -> None:
        check = XIdleTime("name", 100, "logind", re.compile(r"a^"), re.compile(r"a^"))
        mocker.patch.object(check, "_provide_sessions").return_value = [
            XorgSession(42, getuser()),
        ]

        mocker.patch("subprocess.check_output").side_effect = FileNotFoundError

        with pytest.raises(SevereCheckError):
            check.check()
