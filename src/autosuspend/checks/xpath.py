from collections.abc import Sequence
import configparser
from datetime import datetime, timedelta, timezone
from typing import Any

from lxml import etree  # using safe parser
from lxml.etree import XPath, XPathSyntaxError  # our input
import requests
import requests.exceptions

from . import Activity, CheckType, ConfigurationError, TemporaryCheckError, Wakeup
from .util import NetworkMixin


class XPathMixin(NetworkMixin):
    @classmethod
    def collect_init_args(cls, config: configparser.SectionProxy) -> dict[str, Any]:
        try:
            args = NetworkMixin.collect_init_args(config)
            args["xpath"] = config["xpath"].strip()
            # validate the expression
            try:
                XPath(args["xpath"])
            except XPathSyntaxError as error:
                raise ConfigurationError(
                    "Invalid xpath expression: " + args["xpath"]
                ) from error
            return args
        except KeyError as error:
            raise ConfigurationError("Lacks " + str(error) + " config entry") from error

    @classmethod
    def create(
        cls: type[CheckType], name: str, config: configparser.SectionProxy
    ) -> CheckType:
        return cls(name, **cls.collect_init_args(config))  # type: ignore

    def __init__(self, xpath: str, **kwargs: Any) -> None:
        NetworkMixin.__init__(self, **kwargs)
        self._xpath = xpath

        self._parser = etree.XMLParser(resolve_entities=False)

    def evaluate(self) -> Sequence[Any]:
        try:
            reply = self.request().content
            root = etree.fromstring(reply, parser=self._parser)
            return root.xpath(self._xpath)
        except requests.exceptions.RequestException as error:
            raise TemporaryCheckError(error) from error
        except etree.XMLSyntaxError as error:
            raise TemporaryCheckError(error) from error


class XPathActivity(XPathMixin, Activity):
    def __init__(self, name: str, **kwargs: Any) -> None:
        Activity.__init__(self, name)
        XPathMixin.__init__(self, **kwargs)

    def check(self) -> str | None:
        if self.evaluate():
            return "XPath matches for url " + self._url
        else:
            return None


class XPathWakeup(XPathMixin, Wakeup):
    """Determine wake up times from a network resource using XPath expressions.

    The matched results are expected to represent timestamps in seconds UTC.
    """

    def __init__(self, name: str, **kwargs: Any) -> None:
        Wakeup.__init__(self, name)
        XPathMixin.__init__(self, **kwargs)

    def convert_result(
        self,
        result: str,
        timestamp: datetime,  # noqa: ARG002
    ) -> datetime:
        return datetime.fromtimestamp(float(result), timezone.utc)

    def check(self, timestamp: datetime) -> datetime | None:
        matches = self.evaluate()
        try:
            if matches:
                return min(self.convert_result(m, timestamp) for m in matches)
            else:
                return None
        except TypeError as error:
            raise TemporaryCheckError(
                "XPath returned a result that is not a string: " + str(error)
            ) from None
        except ValueError as error:
            raise TemporaryCheckError(
                "Result cannot be parsed: " + str(error)
            ) from error


class XPathDeltaWakeup(XPathWakeup):
    UNITS = (
        "days",
        "seconds",
        "microseconds",
        "milliseconds",
        "minutes",
        "hours",
        "weeks",
    )

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "XPathDeltaWakeup":
        try:
            args = XPathWakeup.collect_init_args(config)
            args["unit"] = config.get("unit", fallback="minutes")
            return cls(name, **args)
        except ValueError as error:
            raise ConfigurationError(str(error)) from error

    def __init__(self, name: str, unit: str, **kwargs: Any) -> None:
        if unit not in self.UNITS:
            raise ValueError("Unsupported unit")
        XPathWakeup.__init__(self, name, **kwargs)
        self._unit = unit

    def convert_result(self, result: str, timestamp: datetime) -> datetime:
        kwargs = {self._unit: float(result)}
        return timestamp + timedelta(**kwargs)
