from getpass import getuser
from pathlib import Path
import re
import subprocess

from dbus.proxies import ProxyObject
import pytest
from pytest_mock import MockerFixture

from autosuspend.checks import (
    Check,
    ConfigurationError,
    SevereCheckError,
    TemporaryCheckError,
)
from autosuspend.checks.activity import LogindSessionsIdle, Smb, XIdleTime
from autosuspend.util.systemd import LogindDBusException
from autosuspend.util.xorg import (
    list_sessions_logind,
    list_sessions_sockets,
    XorgSession,
)

from . import CheckTest
from tests.utils import config_section


class TestSmb(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Smb(name)

    def test_no_connections(self, datadir: Path, mocker: MockerFixture) -> None:
        mocker.patch("subprocess.check_output").return_value = (
            datadir / "smbstatus_no_connections"
        ).read_bytes()

        assert Smb("foo").check() is None

    def test_with_connections(self, datadir: Path, mocker: MockerFixture) -> None:
        mocker.patch("subprocess.check_output").return_value = (
            datadir / "smbstatus_with_connections"
        ).read_bytes()

        res = Smb("foo").check()
        assert res is not None
        assert len(res.splitlines()) == 3

    def test_call_error(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "subprocess.check_output",
            side_effect=subprocess.CalledProcessError(2, "cmd"),
        )

        with pytest.raises(TemporaryCheckError):
            Smb("foo").check()

    def test_missing_executable(self, mocker: MockerFixture) -> None:
        mocker.patch("subprocess.check_output", side_effect=FileNotFoundError)

        with pytest.raises(SevereCheckError):
            Smb("foo").check()

    def test_create(self) -> None:
        assert isinstance(Smb.create("name", None), Smb)


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
