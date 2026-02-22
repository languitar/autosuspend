import configparser
import json
from textwrap import shorten
from typing import Any

import requests
import requests.exceptions
from jsonpath_ng import JSONPath

from . import Activity, ConfigurationError, TemporaryCheckError
from .util import NetworkMixin
from ..config import ParameterType, config_param


@config_param(
    "jsonpath",
    ParameterType.STRING,
    "The JSONPath query to execute. In case it returns a result, the system is assumed to be active.",
    required=True,
)
class JsonPath(NetworkMixin, Activity):
    """Check for activity using JSONPath expressions.

    A generic check which queries a configured URL and expects the reply to contain JSON data.
    The returned JSON document is checked against a configured `JSONPath`_ expression and in case the expression matches, the system is assumed to be active.

    **Requirements**

    * `requests`_
    * `jsonpath-ng`_
    """

    @classmethod
    def collect_init_args(cls, config: configparser.SectionProxy) -> dict[str, Any]:
        from jsonpath_ng.ext import parse

        try:
            args = NetworkMixin.collect_init_args(config)
            args["jsonpath"] = parse(config["jsonpath"])
            return args
        except KeyError as error:
            raise ConfigurationError("Property jsonpath is missing") from error
        except Exception as error:
            raise ConfigurationError(f"JSONPath error {error}") from error

    def __init__(self, name: str, jsonpath: JSONPath, **kwargs: Any) -> None:
        Activity.__init__(self, name)
        NetworkMixin.__init__(self, accept="application/json", **kwargs)
        self._jsonpath = jsonpath

    def check(self) -> str | None:
        try:
            reply = self.request().json()
            matched = self._jsonpath.find(reply)
            if matched:
                # shorten to avoid excessive logging output
                return f"JSONPath {self._jsonpath} found elements " + shorten(
                    str(matched), 24
                )
            return None
        except (json.JSONDecodeError, requests.exceptions.RequestException) as error:
            raise TemporaryCheckError(error) from error
