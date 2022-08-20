import configparser
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Iterable, Optional, Pattern

from dateutil.parser import parse
from dateutil.utils import default_tzinfo
import pytz

from . import Activity, ConfigurationError, TemporaryCheckError


class LastLogActivity(Activity):
    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "LastLogActivity":

        try:
            return cls(
                name,
                Path(config["log_file"]),
                re.compile(config["pattern"]),
                timedelta(minutes=config.getint("minutes", fallback=10)),
                config.get("encoding", "ascii"),
                pytz.timezone(config.get("timezone", "UTC")),  # type: ignore
            )
        except KeyError as error:
            raise ConfigurationError(
                "Missing config key {}".format(error),
            ) from error
        except re.error as error:
            raise ConfigurationError(
                "Regular expression is invalid: {}".format(error),
            ) from error
        except ValueError as error:
            raise ConfigurationError(
                "Unable to parse configuration: {}".format(error),
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
                    "Detected date {} is in the future".format(match_date)
                )
            return match_date
        except ValueError as error:
            raise TemporaryCheckError(
                "Detected date {} cannot be parsed as a date".format(match)
            ) from error
        except OverflowError as error:
            raise TemporaryCheckError(
                "Detected date {} is out of the valid range".format(match)
            ) from error

    def _file_lines_reversed(self) -> Iterable[str]:
        try:
            # Probably not the most effective solution for large log files. Might need
            # optimizations later on.
            return reversed(
                self.log_file.read_text(encoding=self.encoding).splitlines()
            )
        except IOError as error:
            raise TemporaryCheckError(
                "Cannot access log file {}".format(self.log_file)
            ) from error

    def check(self) -> Optional[str]:
        lines = self._file_lines_reversed()

        now = datetime.now(tz=timezone.utc)
        for line in lines:
            match = self.pattern.match(line)
            if not match:
                continue

            match_date = self._safe_parse_date(match.group(1), now)

            # Only check the first line (reverse order) that has a match, not all
            if (now - match_date) < self.delta:
                return "Log activity in {} at {}".format(self.log_file, match_date)
            else:
                return None

        # No line matched at all
        return None
