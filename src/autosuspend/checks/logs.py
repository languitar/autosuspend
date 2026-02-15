import configparser
import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from re import Pattern
from typing import Self
from zoneinfo import ZoneInfo

from dateutil.parser import parse
from dateutil.utils import default_tzinfo

from . import Activity, ConfigurationError, TemporaryCheckError
from ..config import ParameterType, config_param


@config_param(
    "log_file",
    ParameterType.STRING,
    "path to the log file that should be analyzed",
    required=True,
)
@config_param(
    "pattern",
    ParameterType.STRING,
    "A regular expression used to determine whether a line of the log file contains a timestamp to look at. The expression must contain exactly one matching group. For instance, ``^\\[(.*)]\\] .*$`` might be used to find dates in square brackets at line beginnings.",
    required=True,
)
@config_param(
    "minutes",
    ParameterType.INTEGER,
    "The number of minutes to allow log file timestamps to be in the past for detecting activity. If a timestamp is older than ``<now> - <minutes>`` no activity is detected.",
    default=10,
)
@config_param(
    "encoding",
    ParameterType.STRING,
    "The encoding with which to parse the log file.",
    default="ascii",
)
@config_param(
    "timezone",
    ParameterType.STRING,
    "The timezone to assume in case a timestamp extracted from the log file has not associated timezone information. Timezones are expressed using the names from the Olson timezone database (e.g. ``Europe/Berlin``).",
    default="UTC",
)
class LastLogActivity(Activity):
    @classmethod
    def create(cls: type[Self], name: str, config: configparser.SectionProxy) -> Self:
        try:
            return cls(
                name,
                Path(config["log_file"]),
                re.compile(config["pattern"]),
                timedelta(minutes=config.getint("minutes", fallback=10)),
                config.get("encoding", "ascii"),
                ZoneInfo(config.get("timezone", "UTC")),  # type: ignore
            )
        except KeyError as error:
            raise ConfigurationError(
                f"Missing config key {error}",
            ) from error
        except re.error as error:
            raise ConfigurationError(
                f"Regular expression is invalid: {error}",
            ) from error
        except ValueError as error:
            raise ConfigurationError(
                f"Unable to parse configuration: {error}",
            ) from error

    def __init__(
        self,
        name: str,
        log_file: Path,
        pattern: Pattern,
        delta: timedelta,
        encoding: str,
        default_timezone: timezone,
    ) -> None:
        if delta.total_seconds() < 0:
            raise ValueError("Given delta must be positive")
        if pattern.groups != 1:
            raise ValueError("Given pattern must have exactly one capture group")
        super().__init__(name=name)
        self.log_file = log_file
        self.pattern = pattern
        self.delta = delta
        self.encoding = encoding
        self.default_timezone = default_timezone

    def _safe_parse_date(self, match: str, now: datetime) -> datetime:
        try:
            match_date = default_tzinfo(parse(match), self.default_timezone)
            if match_date > now:
                raise TemporaryCheckError(
                    f"Detected date {match_date} is in the future"
                )
            return match_date
        except ValueError as error:
            raise TemporaryCheckError(
                f"Detected date {match} cannot be parsed as a date"
            ) from error
        except OverflowError as error:
            raise TemporaryCheckError(
                f"Detected date {match} is out of the valid range"
            ) from error

    def _file_lines_reversed(self) -> Iterable[str]:
        try:
            # Probably not the most effective solution for large log files. Might need
            # optimizations later on.
            return reversed(
                self.log_file.read_text(encoding=self.encoding).splitlines()
            )
        except OSError as error:
            raise TemporaryCheckError(
                f"Cannot access log file {self.log_file}"
            ) from error

    def check(self) -> str | None:
        lines = self._file_lines_reversed()

        now = datetime.now(UTC)
        for line in lines:
            match = self.pattern.match(line)
            if not match:
                continue

            match_date = self._safe_parse_date(match.group(1), now)

            # Only check the first line (reverse order) that has a match, not all
            if (now - match_date) < self.delta:
                return f"Log activity in {self.log_file} at {match_date}"
            else:
                return None

        # No line matched at all
        return None
