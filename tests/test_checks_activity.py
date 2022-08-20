from datetime import timedelta, timezone
from getpass import getuser
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Tuple

from dbus.proxies import ProxyObject
from freezegun import freeze_time
from jsonpath_ng.ext import parse
import pytest
from pytest_mock import MockerFixture
import pytz

from autosuspend.checks import (
    Check,
    ConfigurationError,
    SevereCheckError,
    TemporaryCheckError,
)
from autosuspend.checks.activity import (
    JsonPath,
    LastLogActivity,
    LogindSessionsIdle,
    Smb,
    XIdleTime,
)
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


class TestJsonPath(CheckTest):
    def create_instance(self, name: str) -> JsonPath:
        return JsonPath(
            name=name,
            url="url",
            timeout=5,
            username="userx",
            password="pass",
            jsonpath=parse("b"),
        )

    @staticmethod
    @pytest.fixture()
    def json_get_mock(mocker: Any) -> Any:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"a": {"b": 42, "c": "ignore"}}
        return mocker.patch("requests.Session.get", return_value=mock_reply)

    def test_matching(self, json_get_mock: Any) -> None:
        url = "nourl"
        assert (
            JsonPath("foo", jsonpath=parse("a.b"), url=url, timeout=5).check()
            is not None
        )

        json_get_mock.assert_called_once_with(
            url, timeout=5, headers={"Accept": "application/json"}
        )
        json_get_mock().json.assert_called_once()

    def test_filter_expressions_work(self, json_get_mock: Any) -> None:
        url = "nourl"
        assert (
            JsonPath(
                "foo", jsonpath=parse("$[?(@.c=='ignore')]"), url=url, timeout=5
            ).check()
            is not None
        )

        json_get_mock.assert_called_once_with(
            url, timeout=5, headers={"Accept": "application/json"}
        )
        json_get_mock().json.assert_called_once()

    def test_not_matching(self, json_get_mock: Any) -> None:
        url = "nourl"
        assert (
            JsonPath("foo", jsonpath=parse("not.there"), url=url, timeout=5).check()
            is None
        )

        json_get_mock.assert_called_once_with(
            url, timeout=5, headers={"Accept": "application/json"}
        )
        json_get_mock().json.assert_called_once()

    def test_network_errors_are_passed(
        self, datadir: Path, serve_protected: Callable[[Path], Tuple[str, str, str]]
    ) -> None:
        with pytest.raises(TemporaryCheckError):
            JsonPath(
                name="name",
                url=serve_protected(datadir / "data.txt")[0],
                timeout=5,
                username="wrong",
                password="wrong",
                jsonpath=parse("b"),
            ).check()

    def test_not_json(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        with pytest.raises(TemporaryCheckError):
            JsonPath(
                name="name",
                url=serve_file(datadir / "invalid.json"),
                timeout=5,
                jsonpath=parse("b"),
            ).check()

    def test_create(self) -> None:
        check: JsonPath = JsonPath.create(
            "name",
            config_section(
                {
                    "url": "url",
                    "jsonpath": "a.b",
                    "username": "user",
                    "password": "pass",
                    "timeout": "42",
                }
            ),
        )  # type: ignore
        assert check._jsonpath == parse("a.b")
        assert check._url == "url"
        assert check._username == "user"
        assert check._password == "pass"
        assert check._timeout == 42

    def test_create_missing_path(self) -> None:
        with pytest.raises(ConfigurationError):
            JsonPath.create(
                "name",
                config_section(
                    {
                        "url": "url",
                        "username": "user",
                        "password": "pass",
                        "timeout": "42",
                    }
                ),
            )

    def test_create_invalid_path(self) -> None:
        with pytest.raises(ConfigurationError):
            JsonPath.create(
                "name",
                config_section(
                    {
                        "url": "url",
                        "jsonpath": ",.asdfjasdklf",
                        "username": "user",
                        "password": "pass",
                        "timeout": "42",
                    }
                ),
            )


class TestLastLogActivity(CheckTest):
    def create_instance(self, name: str) -> LastLogActivity:
        return LastLogActivity(
            name=name,
            log_file=Path("some_file"),
            pattern=re.compile("^(.*)$"),
            delta=timedelta(minutes=10),
            encoding="ascii",
            default_timezone=timezone.utc,
        )

    def test_is_active(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        file_path.write_text("2020-02-02 12:12:23", encoding="ascii")

        with freeze_time("2020-02-02 12:15:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^(.*)$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone.utc,
                ).check()
                is not None
            )

    def test_is_not_active(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        file_path.write_text("2020-02-02 12:12:23", encoding="ascii")

        with freeze_time("2020-02-02 12:35:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^(.*)$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone.utc,
                ).check()
                is None
            )

    def test_uses_last_line(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        # last line is too old and must be used
        file_path.write_text(
            "\n".join(["2020-02-02 12:12:23", "1900-01-01"]), encoding="ascii"
        )

        with freeze_time("2020-02-02 12:15:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^(.*)$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone.utc,
                ).check()
                is None
            )

    def test_ignores_lines_that_do_not_match(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        file_path.write_text("ignored", encoding="ascii")

        assert (
            LastLogActivity(
                "test",
                file_path,
                re.compile(r"^foo(.*)$"),
                timedelta(minutes=10),
                "ascii",
                timezone.utc,
            ).check()
            is None
        )

    def test_uses_pattern(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        file_path.write_text("foo2020-02-02 12:12:23bar", encoding="ascii")

        with freeze_time("2020-02-02 12:15:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^foo(.*)bar$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone.utc,
                ).check()
                is not None
            )

    def test_uses_given_timezone(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        # would match if timezone wasn't used
        file_path.write_text("2020-02-02 12:12:00", encoding="ascii")

        with freeze_time("2020-02-02 12:15:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^(.*)$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone(offset=timedelta(hours=10)),
                ).check()
                is None
            )

    def test_prefers_parsed_timezone(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        # would not match if provided timezone wasn't used
        file_path.write_text("2020-02-02T12:12:01-01:00", encoding="ascii")

        with freeze_time("2020-02-02 13:15:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^(.*)$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone.utc,
                ).check()
                is not None
            )

    def test_fails_if_dates_cannot_be_parsed(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        # would match if timezone wasn't used
        file_path.write_text("202000xxx", encoding="ascii")

        with pytest.raises(TemporaryCheckError):
            LastLogActivity(
                "test",
                file_path,
                re.compile(r"^(.*)$"),
                timedelta(minutes=10),
                "ascii",
                timezone.utc,
            ).check()

    def test_fails_if_dates_are_in_the_future(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        # would match if timezone wasn't used
        file_path.write_text("2022-01-01", encoding="ascii")

        with freeze_time("2020-02-02 12:15:00"), pytest.raises(TemporaryCheckError):
            LastLogActivity(
                "test",
                file_path,
                re.compile(r"^(.*)$"),
                timedelta(minutes=10),
                "ascii",
                timezone.utc,
            ).check()

    def test_fails_if_file_cannot_be_read(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"

        with pytest.raises(TemporaryCheckError):
            LastLogActivity(
                "test",
                file_path,
                re.compile(r"^(.*)$"),
                timedelta(minutes=10),
                "ascii",
                timezone.utc,
            ).check()

    def test_create(self) -> None:
        created = LastLogActivity.create(
            "thename",
            config_section(
                {
                    "name": "somename",
                    "log_file": "/some/file",
                    "pattern": "^foo(.*)bar$",
                    "minutes": "42",
                    "encoding": "utf-8",
                    "timezone": "Europe/Berlin",
                }
            ),
        )

        assert created.log_file == Path("/some/file")
        assert created.pattern == re.compile(r"^foo(.*)bar$")
        assert created.delta == timedelta(minutes=42)
        assert created.encoding == "utf-8"
        assert created.default_timezone == pytz.timezone("Europe/Berlin")

    def test_create_handles_pattern_errors(self) -> None:
        with pytest.raises(ConfigurationError):
            LastLogActivity.create(
                "thename",
                config_section(
                    {
                        "name": "somename",
                        "log_file": "/some/file",
                        "pattern": "^^foo((.*)bar$",
                    }
                ),
            )

    def test_create_handles_delta_errors(self) -> None:
        with pytest.raises(ConfigurationError):
            LastLogActivity.create(
                "thename",
                config_section(
                    {
                        "name": "somename",
                        "log_file": "/some/file",
                        "pattern": "(.*)",
                        "minutes": "test",
                    }
                ),
            )

    def test_create_handles_negative_deltas(self) -> None:
        with pytest.raises(ConfigurationError):
            LastLogActivity.create(
                "thename",
                config_section(
                    {
                        "name": "somename",
                        "log_file": "/some/file",
                        "pattern": "(.*)",
                        "minutes": "-42",
                    }
                ),
            )

    def test_create_handles_missing_pattern_groups(self) -> None:
        with pytest.raises(ConfigurationError):
            LastLogActivity.create(
                "thename",
                config_section(
                    {
                        "name": "somename",
                        "log_file": "/some/file",
                        "pattern": ".*",
                    }
                ),
            )

    def test_create_handles_missing_keys(self) -> None:
        with pytest.raises(ConfigurationError):
            LastLogActivity.create(
                "thename",
                config_section(
                    {
                        "name": "somename",
                    }
                ),
            )
