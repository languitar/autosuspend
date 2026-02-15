import configparser
import json
from typing import Any, Self

from . import Activity, ConfigurationError, TemporaryCheckError
from .util import NetworkMixin
from ..config import ParameterType, config_param


def _add_default_kodi_url(config: configparser.SectionProxy) -> None:
    if "url" not in config:
        config["url"] = "http://localhost:8080/jsonrpc"


@config_param(
    "url",
    ParameterType.STRING,
    "Base URL of the JSON RPC API of the Kodi instance",
    default="http://localhost:8080/jsonrpc",
)
@config_param(
    "suspend_while_paused",
    ParameterType.BOOLEAN,
    "Also suspend the system when media playback is paused instead of only suspending when playback is stopped.",
    default=False,
)
class Kodi(NetworkMixin, Activity):
    """Check for Kodi media player activity.

    Checks whether an instance of `Kodi`_ is currently playing.

    **Requirements**

    * `requests`_
    """

    @classmethod
    def collect_init_args(cls, config: configparser.SectionProxy) -> dict[str, Any]:
        try:
            _add_default_kodi_url(config)
            args = NetworkMixin.collect_init_args(config)
            args["suspend_while_paused"] = config.getboolean(
                "suspend_while_paused", fallback=False
            )
            return args
        except ValueError as error:
            raise ConfigurationError(f"Configuration error {error}") from error

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> Self:
        return cls(name, **cls.collect_init_args(config))

    def __init__(
        self, name: str, url: str, suspend_while_paused: bool = False, **kwargs: Any
    ) -> None:
        self._suspend_while_paused = suspend_while_paused
        if self._suspend_while_paused:
            request = url + (
                '?request={"jsonrpc": "2.0", "id": 1, '
                '"method": "XBMC.GetInfoBooleans",'
                '"params": {"booleans": ["Player.Playing"]} }'
            )
        else:
            request = url + (
                '?request={"jsonrpc": "2.0", "id": 1, '
                '"method": "Player.GetActivePlayers"}'
            )
        NetworkMixin.__init__(self, url=request, **kwargs)
        Activity.__init__(self, name)

    def _safe_request_result(self) -> dict:
        try:
            return self.request().json()["result"]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise TemporaryCheckError("Unable to get or parse Kodi state") from error

    def check(self) -> str | None:
        reply = self._safe_request_result()
        if self._suspend_while_paused:
            return (
                "Kodi actively playing media" if reply.get("Player.Playing") else None
            )
        else:
            return "Kodi currently playing" if reply else None


@config_param(
    "url",
    ParameterType.STRING,
    "Base URL of the JSON RPC API of the Kodi instance",
    default="http://localhost:8080/jsonrpc",
)
@config_param(
    "idle_time",
    ParameterType.INTEGER,
    "Marks the system active in case a user interaction has appeared within the this amount of seconds until now.",
    default=120,
)
class KodiIdleTime(NetworkMixin, Activity):
    """Check for Kodi user interface activity.

    Checks whether there has been interaction with the Kodi user interface recently.
    This prevents suspending the system in case someone is currently browsing collections etc.
    This check is redundant to :ref:`check-x-idle-time` on systems using an X server, but might be necessary in case Kodi is used standalone.
    It does not replace the :ref:`check-kodi` check, as the idle time is not updated when media is playing.

    **Requirements**

    * `requests`_
    """

    @classmethod
    def collect_init_args(cls, config: configparser.SectionProxy) -> dict[str, Any]:
        try:
            _add_default_kodi_url(config)
            args = NetworkMixin.collect_init_args(config)
            args["idle_time"] = config.getint("idle_time", fallback=120)
            return args
        except ValueError as error:
            raise ConfigurationError("Configuration error " + str(error)) from error

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> Self:
        return cls(name, **cls.collect_init_args(config))

    def __init__(self, name: str, url: str, idle_time: int, **kwargs: Any) -> None:
        request = url + (
            '?request={"jsonrpc": "2.0", "id": 1, '
            '"method": "XBMC.GetInfoBooleans",'
            f'"params": {{"booleans": ["System.IdleTime({idle_time})"]}}}}'
        )
        NetworkMixin.__init__(self, url=request, **kwargs)
        Activity.__init__(self, name)
        self._idle_time = idle_time

    def check(self) -> str | None:
        try:
            reply = self.request().json()
            if not reply["result"][f"System.IdleTime({self._idle_time})"]:
                return "Someone interacts with Kodi"
            else:
                return None
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise TemporaryCheckError("Unable to get or parse Kodi state") from error
