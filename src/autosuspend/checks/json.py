import configparser
import json
from textwrap import shorten
from typing import Any, Dict, Optional

from jsonpath_ng import JSONPath
import requests
import requests.exceptions

from . import Activity, ConfigurationError, TemporaryCheckError
from .util import NetworkMixin


class JsonPath(NetworkMixin, Activity):
    """Requests a URL and evaluates whether a JSONPath expression matches."""

    @classmethod
    def collect_init_args(cls, config: configparser.SectionProxy) -> Dict[str, Any]:
        from jsonpath_ng.ext import parse

        try:
            args = NetworkMixin.collect_init_args(config)
            args["jsonpath"] = parse(config["jsonpath"])
            return args
        except KeyError as error:
            raise ConfigurationError("Property jsonpath is missing") from error
        except Exception as error:
            raise ConfigurationError(f"JSONPath error {str(error)}") from error

    def __init__(self, name: str, jsonpath: JSONPath, **kwargs: Any) -> None:
        Activity.__init__(self, name)
        NetworkMixin.__init__(self, accept="application/json", **kwargs)
        self._jsonpath = jsonpath

    def check(self) -> Optional[str]:
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
