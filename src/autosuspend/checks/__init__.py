"""Provides the basic types used for checks."""

import abc
import configparser
from datetime import datetime
from typing import Any, Mapping, Optional, Type, TypeVar

from autosuspend.util import logger_by_class_instance


class ConfigurationError(RuntimeError):
    """Indicates an error in the configuration of a :class:`Check`."""

    pass


class TemporaryCheckError(RuntimeError):
    """
    Indicates a temporary error while performing a check.

    Such an error can be ignored for some time since it might recover
    automatically.
    """

    pass


class SevereCheckError(RuntimeError):
    """
    Indicates a sever check error that will probably not recover.

    There is no hope this situation recovers.
    """

    pass


CheckType = TypeVar("CheckType", bound="Check")


class Check(abc.ABC):
    """Base class for all kinds of checks.

    Subclasses must call this class' ``__init__`` method.

    Args:
        name (str):
            Configured name of the check
    """

    @classmethod
    @abc.abstractmethod
    def create(
        cls: Type[CheckType], name: str, config: configparser.SectionProxy
    ) -> CheckType:
        """Create a new check instance from the provided configuration.

        Args:
            name:
                user-defined name for the check
            config:
                config parser section with the configuration for this check

        Raises:
            ConfigurationError:
                Configuration for this check is inappropriate

        """
        pass

    def __init__(self, name: Optional[str] = None) -> None:
        if name:
            self.name = name
        else:
            self.name = self.__class__.__name__
        self.logger = logger_by_class_instance(self, name)

    def options(self) -> Mapping[str, Any]:
        """Return the configured options as a mapping.

        This is used for debugging purposes only.
        """
        return {
            k: v for k, v in self.__dict__.items() if not callable(v) and k != "logger"
        }

    def __str__(self) -> str:
        return "{name}[class={clazz}]".format(
            name=self.name, clazz=self.__class__.__name__
        )


class Activity(Check):
    """Base class for activity checks.

    Subclasses must call this class' __init__ method.
    """

    @abc.abstractmethod
    def check(self) -> Optional[str]:
        """Determine if system activity exists that prevents suspending.

        Returns:
            A string describing which condition currently prevents sleep, else ``None``.

        Raises:
            TemporaryCheckError:
                Check execution currently fails but might recover later
            SevereCheckError:
                Check executions fails severely
        """
        pass

    def __str__(self) -> str:
        return "{name}[class={clazz}]".format(
            name=self.name, clazz=self.__class__.__name__
        )


class Wakeup(Check):
    """Represents a check for potential wake up points."""

    @abc.abstractmethod
    def check(self, timestamp: datetime) -> Optional[datetime]:
        """Indicate if a wakeup has to be scheduled for this check.

        Args:
            timestamp:
                the time at which the call to the wakeup check is made

        Returns:
            a datetime describing when the system needs to be running again or
            ``None`` if no wakeup is required. Use timezone aware datetimes.

        Raises:
            TemporaryCheckError:
                Check execution currently fails but might recover later
            SevereCheckError:
                Check executions fails severely
        """
        pass
