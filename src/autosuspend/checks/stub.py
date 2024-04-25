import configparser
from datetime import datetime, timedelta

from . import ConfigurationError, Wakeup


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
            raise ConfigurationError(str(error)) from error

    def __init__(self, name: str, delta: timedelta) -> None:
        Wakeup.__init__(self, name)
        self._delta = delta

    def check(self, timestamp: datetime) -> datetime | None:
        return timestamp + self._delta
