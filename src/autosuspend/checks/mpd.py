import configparser
import socket
from typing import Self

from mpd import MPDClient, MPDError

from . import Activity, Check, ConfigurationError, TemporaryCheckError


class Mpd(Activity):
    @classmethod
    def create(cls: type[Self], name: str, config: configparser.SectionProxy) -> Self:
        try:
            host = config.get("host", fallback="localhost")
            port = config.getint("port", fallback=6600)
            timeout = config.getint("timeout", fallback=5)
            return cls(name, host, port, timeout)
        except ValueError as error:
            raise ConfigurationError(
                f"Host port or timeout configuration wrong: {error}"
            ) from error

    def __init__(self, name: str, host: str, port: int, timeout: float) -> None:
        Check.__init__(self, name)
        self._host = host
        self._port = port
        self._timeout = timeout

    def _get_state(self) -> dict:
        client = MPDClient()
        client.timeout = self._timeout
        client.connect(self._host, self._port)
        state = client.status()
        client.close()
        client.disconnect()
        return state

    def check(self) -> str | None:
        try:
            state = self._get_state()
            if state["state"] == "play":
                return "MPD currently playing"
            else:
                return None
        except (TimeoutError, MPDError, ConnectionError, socket.gaierror) as error:
            raise TemporaryCheckError("Unable to get the current MPD state") from error
