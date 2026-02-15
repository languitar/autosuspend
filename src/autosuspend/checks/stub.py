import configparser
from datetime import datetime, timedelta
from typing import Self

from . import ConfigurationError, Wakeup
from ..config import ParameterType, config_param


@config_param(
    "unit",
    ParameterType.STRING,
    "A string indicating in which unit the delta is specified. Valid options are: ``microseconds``, ``milliseconds``, ``seconds``, ``minutes``, ``hours``, ``days``, ``weeks``.",
    required=True,
    enum_values=[
        "microseconds",
        "milliseconds",
        "seconds",
        "minutes",
        "hours",
        "days",
        "weeks",
    ],
)
@config_param(
    "value",
    ParameterType.FLOAT,
    "The value of the delta as an int.",
    required=True,
)
class Periodic(Wakeup):
    """Always indicates a wake up after a specified delta of time from now on.

    Use this to periodically wake up a system.
    """

    @classmethod
    def create(cls: type[Self], name: str, config: configparser.SectionProxy) -> Self:
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
