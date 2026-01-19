import re
from datetime import UTC, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from autosuspend.checks import ConfigurationError, TemporaryCheckError
from autosuspend.checks.logs import LastLogActivity

from . import CheckTest
from .utils import config_section


class TestLastLogActivity(CheckTest):
    def create_instance(self, name: str) -> LastLogActivity:
        return LastLogActivity(
            name=name,
            log_file=Path("some_file"),
            pattern=re.compile("^(.*)$"),
            delta=timedelta(minutes=10),
            encoding="ascii",
            default_timezone=UTC,
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
                    UTC,
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
                    UTC,
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
                    UTC,
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
                UTC,
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
                    UTC,
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
                    UTC,
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
                UTC,
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
                UTC,
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
                UTC,
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
        assert created.default_timezone == ZoneInfo("Europe/Berlin")

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
