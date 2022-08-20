import configparser  # noqa
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Optional

from . import ConfigurationError, Wakeup


# isort: off

from .linux import File  # noqa
from .command import CommandWakeup as Command  # noqa

with suppress(ModuleNotFoundError):
    from .ical import Calendar  # noqa
with suppress(ModuleNotFoundError):
    from .xpath import XPathWakeup as XPath  # noqa
    from .xpath import XPathDeltaWakeup as XPathDelta  # noqa
with suppress(ModuleNotFoundError):
    from .systemd import SystemdTimer  # noqa

# isort: on


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
