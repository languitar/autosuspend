import configparser  # noqa
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
from typing import Optional

from . import ConfigurationError, TemporaryCheckError, Wakeup
from .util import CommandMixin
from ..util.subprocess import raise_severe_if_command_not_found


# isort: off

with suppress(ModuleNotFoundError):
    from .ical import Calendar  # noqa
with suppress(ModuleNotFoundError):
    from .xpath import XPathWakeup as XPath  # noqa
    from .xpath import XPathDeltaWakeup as XPathDelta  # noqa
with suppress(ModuleNotFoundError):
    from .systemd import SystemdTimer  # noqa

# isort: on


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
            kwargs = {config["unit"]: float(config["value"])}
            return cls(name, timedelta(**kwargs))
        except (ValueError, KeyError, TypeError) as error:
            raise ConfigurationError(str(error))

    def __init__(self, name: str, delta: timedelta) -> None:
        Wakeup.__init__(self, name)
        self._delta = delta

    def check(self, timestamp: datetime) -> Optional[datetime]:
        return timestamp + self._delta
