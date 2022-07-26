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
from autosuspend.checks.wakeup import (
    Command,
    File,
    Periodic,
    SystemdTimer,
    XPath,
    XPathDelta,
)

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


class TestXPath(CheckTest):
    def create_instance(self, name: str) -> Check:
        return XPath(name, xpath="/a", url="nourl", timeout=5)

    def test_matching(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = '<a value="42.3"></a>'
        mock_method = mocker.patch("requests.Session.get", return_value=mock_reply)

        url = "nourl"
        assert XPath("foo", xpath="/a/@value", url=url, timeout=5).check(
            datetime.now(timezone.utc)
        ) == datetime.fromtimestamp(42.3, timezone.utc)

        mock_method.assert_called_once_with(url, timeout=5, headers=None)
        content_property.assert_called_once_with()

    def test_not_matching(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert (
            XPath("foo", xpath="/b", url="nourl", timeout=5).check(
                datetime.now(timezone.utc)
            )
            is None
        )

    def test_not_a_string(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            XPath("foo", xpath="/a", url="nourl", timeout=5).check(
                datetime.now(timezone.utc)
            )

    def test_not_a_number(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = '<a value="narf"></a>'
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            XPath("foo", xpath="/a/@value", url="nourl", timeout=5).check(
                datetime.now(timezone.utc)
            )

    def test_multiple_min(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = """
            <root>
                <a value="40"></a>
                <a value="10"></a>
                <a value="20"></a>
            </root>
        """
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert XPath("foo", xpath="//a/@value", url="nourl", timeout=5).check(
            datetime.now(timezone.utc)
        ) == datetime.fromtimestamp(10, timezone.utc)

    def test_create(self) -> None:
        check: XPath = XPath.create(
            "name",
            config_section(
                {
                    "xpath": "/valid",
                    "url": "nourl",
                    "timeout": "20",
                }
            ),
        )  # type: ignore
        assert check._xpath == "/valid"


class TestXPathDelta(CheckTest):
    def create_instance(self, name: str) -> Check:
        return XPathDelta(name, xpath="/a", url="nourl", timeout=5, unit="days")

    @pytest.mark.parametrize(
        ("unit", "factor"),
        [
            ("microseconds", 0.000001),
            ("milliseconds", 0.001),
            ("seconds", 1),
            ("minutes", 60),
            ("hours", 60 * 60),
            ("days", 60 * 60 * 24),
            ("weeks", 60 * 60 * 24 * 7),
        ],
    )
    def test_smoke(self, mocker: MockFixture, unit: str, factor: float) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = '<a value="42"></a>'
        mocker.patch("requests.Session.get", return_value=mock_reply)

        url = "nourl"
        now = datetime.now(timezone.utc)
        result = XPathDelta(
            "foo", xpath="/a/@value", url=url, timeout=5, unit=unit
        ).check(now)
        assert result == now + timedelta(seconds=42) * factor

    def test_create(self) -> None:
        check = XPathDelta.create(
            "name",
            config_section(
                {
                    "xpath": "/valid",
                    "url": "nourl",
                    "timeout": "20",
                    "unit": "weeks",
                }
            ),
        )
        assert check._unit == "weeks"

    def test_create_wrong_unit(self) -> None:
        with pytest.raises(ConfigurationError):
            XPathDelta.create(
                "name",
                config_section(
                    {
                        "xpath": "/valid",
                        "url": "nourl",
                        "timeout": "20",
                        "unit": "unknown",
                    }
                ),
            )

    def test_init_wrong_unit(self) -> None:
        with pytest.raises(ValueError, match=r".*unit.*"):
            XPathDelta("name", url="url", xpath="/a", timeout=5, unit="unknownunit")
