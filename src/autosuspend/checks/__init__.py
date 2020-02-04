"""Provides the basic types used for checks."""

import abc
import datetime
from typing import Optional

from .config import Configuration, ConfigurationError, Options
from ..util import logger_by_class_instance


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


class Check(abc.ABC):
    """
    Base class for all kinds of checks.

    Subclasses must call this class' ``__init__`` method.

    Check instances need to be configured with a call to ``configure`` before being
    usable. The caller/user guarantees this fact.

    Args:
        name (str):
            Configured name of the check
    """

    def __init__(self, name: str = None) -> None:
        self.name = name or self.__class__.__name__
        self.logger = logger_by_class_instance(self, name)

    @classmethod
    @property
    def options(cls) -> Options:
        options = Options()
        cls._provide_options(options)
        return options

    @classmethod
    @abc.abstractmethod
    def _provide_options(cls, holder: Options) -> None:
        pass

    @property
    def configuration(self) -> Configuration:
        """
        Return the current configuration of the check.

        This is used for debugging purposes only.
        """
        assert self._configuration
        return self._configuration

    def __str__(self) -> str:
        return "{name}[class={clazz}]".format(
            name=self.name, clazz=self.__class__.__name__
        )


class Activity(Check):
    """
    Base class for activity checks.

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


class Wakeup(Check):
    """Represents a check for potential wake up points."""

    @abc.abstractmethod
    def check(self, timestamp: datetime.datetime) -> Optional[datetime.datetime]:
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
