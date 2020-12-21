import configparser
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import subprocess
from typing import Any, Optional

from . import ConfigurationError, TemporaryCheckError, Wakeup
from .util import CommandMixin, NetworkMixin, XPathMixin
from ..util.subprocess import raise_severe_if_command_not_found


class Calendar(NetworkMixin, Wakeup):
    """Uses an ical calendar to wake up on the next scheduled event."""

    def __init__(self, name: str, **kwargs: Any) -> None:
        NetworkMixin.__init__(self, **kwargs)
        Wakeup.__init__(self, name)

    def check(self, timestamp: datetime) -> Optional[datetime]:
        from ..util.ical import list_calendar_events

        response = self.request()

        end = timestamp + timedelta(weeks=6 * 4)
        events = list_calendar_events(BytesIO(response.content), timestamp, end)
        # Filter out currently active events. They are not our business.
        events = [e for e in events if e.start >= timestamp]

        if events:
            candidate = events[0]
            if isinstance(candidate.start, datetime):
                return candidate.start
            else:
                return datetime.combine(candidate.start, datetime.min.time())
        else:
            return None


class File(Wakeup):
    """Determines scheduled wake ups from the contents of a file on disk.

    File contents are interpreted as a Unix timestamp in seconds UTC.
    """

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "File":
        try:
            path = Path(config["path"])
            return cls(name, path)
        except KeyError as error:
            raise ConfigurationError("Missing option path") from error

    def __init__(self, name: str, path: Path) -> None:
        Wakeup.__init__(self, name)
        self._path = path

    def check(self, timestamp: datetime) -> Optional[datetime]:
        try:
            first_line = self._path.read_text().splitlines()[0]
            return datetime.fromtimestamp(float(first_line.strip()), timezone.utc)
        except FileNotFoundError:
            # this is ok
            return None
        except (ValueError, IOError) as error:
            raise TemporaryCheckError(
                "Next wakeup time cannot be read despite a file being present"
            ) from error


class Command(CommandMixin, Wakeup):
    """Determine wake up times based on an external command.

    The called command must return a timestamp in UTC or nothing in case no
    wake up is planned.
    """

    def __init__(self, name: str, command: str) -> None:
        CommandMixin.__init__(self, command)
        Wakeup.__init__(self, name)

    def check(self, timestamp: datetime) -> Optional[datetime]:
        try:
            output = subprocess.check_output(
                self._command,
                shell=True,  # noqa: S602
            ).splitlines()[0]
            self.logger.debug(
                "Command %s succeeded with output %s", self._command, output
            )
            if output.strip():
                return datetime.fromtimestamp(float(output.strip()), timezone.utc)
            else:
                return None

        except subprocess.CalledProcessError as error:
            raise_severe_if_command_not_found(error)
            raise TemporaryCheckError(
                "Unable to call the configured command"
            ) from error
        except ValueError as error:
            raise TemporaryCheckError(
                "Return value cannot be interpreted as a timestamp"
            ) from error


class Periodic(Wakeup):
    """Always indicates a wake up after a specified delta of time from now on.

    Use this to periodically wake up a system.
    """

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "Periodic":
        try:
            kwargs = {}
            kwargs[config["unit"]] = float(config["value"])
            return cls(name, timedelta(**kwargs))  # type: ignore
        except (ValueError, KeyError, TypeError) as error:
            raise ConfigurationError(str(error))

    def __init__(self, name: str, delta: timedelta) -> None:
        Wakeup.__init__(self, name)
        self._delta = delta

    def check(self, timestamp: datetime) -> Optional[datetime]:
        return timestamp + self._delta


class XPath(XPathMixin, Wakeup):
    """Determine wake up times from a network resource using XPath expressions.

    The matched results are expected to represent timestamps in seconds UTC.
    """

    def __init__(self, name: str, **kwargs: Any) -> None:
        Wakeup.__init__(self, name)
        XPathMixin.__init__(self, **kwargs)

    def convert_result(self, result: str, timestamp: datetime) -> datetime:
        return datetime.fromtimestamp(float(result), timezone.utc)

    def check(self, timestamp: datetime) -> Optional[datetime]:
        matches = self.evaluate()
        try:
            if matches:
                return min(self.convert_result(m, timestamp) for m in matches)
            else:
                return None
        except TypeError as error:
            raise TemporaryCheckError(
                "XPath returned a result that is not a string: " + str(error)
            )
        except ValueError as error:
            raise TemporaryCheckError("Result cannot be parsed: " + str(error))


class XPathDelta(XPath):

    UNITS = [
        "days",
        "seconds",
        "microseconds",
        "milliseconds",
        "minutes",
        "hours",
        "weeks",
    ]

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "XPathDelta":
        try:
            args = XPath.collect_init_args(config)
            args["unit"] = config.get("unit", fallback="minutes")
            return cls(name, **args)
        except ValueError as error:
            raise ConfigurationError(str(error))

    def __init__(self, name: str, unit: str, **kwargs: Any) -> None:
        if unit not in self.UNITS:
            raise ValueError("Unsupported unit")
        XPath.__init__(self, name, **kwargs)
        self._unit = unit

    def convert_result(self, result: str, timestamp: datetime) -> datetime:
        kwargs = {}
        kwargs[self._unit] = float(result)
        return timestamp + timedelta(**kwargs)  # type: ignore
