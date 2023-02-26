import configparser
from contextlib import suppress
from typing import Any, Dict, Optional, TYPE_CHECKING

from . import Check, ConfigurationError, SevereCheckError, TemporaryCheckError


if TYPE_CHECKING:
    import requests
    import requests.models


class NetworkMixin:
    @staticmethod
    def _ensure_credentials_consistent(args: Dict[str, Any]) -> None:
        if (args["username"] is None) != (args["password"] is None):
            raise ConfigurationError("Username and password must be set")

    @classmethod
    def collect_init_args(  # noqa: CCR001
        cls,
        config: configparser.SectionProxy,
    ) -> Dict[str, Any]:
        try:
            args: Dict[str, Any] = {}
            args["timeout"] = config.getint("timeout", fallback=5)
            args["url"] = config["url"]
            args["username"] = config.get("username")
            args["password"] = config.get("password")
            cls._ensure_credentials_consistent(args)
            return args
        except ValueError as error:
            raise ConfigurationError("Configuration error " + str(error)) from error
        except KeyError as error:
            raise ConfigurationError("Lacks " + str(error) + " config entry") from error

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> Check:
        return cls(name, **cls.collect_init_args(config))  # type: ignore

    def __init__(
        self,
        url: str,
        timeout: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        accept: Optional[str] = None,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._username = username
        self._password = password
        self._accept = accept

    @staticmethod
    def _create_session() -> "requests.Session":
        import requests

        session = requests.Session()

        with suppress(ImportError):
            from requests_file import FileAdapter

            session.mount("file://", FileAdapter())

        return session

    def _request_headers(self) -> Optional[Dict[str, str]]:
        if self._accept:
            return {"Accept": self._accept}
        else:
            return None

    def _create_auth_from_failed_request(
        self,
        reply: "requests.models.Response",
        username: str,
        password: str,
    ) -> Any:
        from requests.auth import HTTPBasicAuth, HTTPDigestAuth

        auth_map = {
            "basic": HTTPBasicAuth,
            "digest": HTTPDigestAuth,
        }

        auth_scheme = reply.headers["WWW-Authenticate"].split(" ")[0].lower()
        if auth_scheme not in auth_map:
            raise SevereCheckError(
                "Unsupported authentication scheme {}".format(auth_scheme)
            )

        return auth_map[auth_scheme](username, password)

    def request(self) -> "requests.models.Response":
        import requests
        import requests.exceptions

        session = self._create_session()

        try:
            reply = session.get(
                self._url, timeout=self._timeout, headers=self._request_headers()
            )

            # replace reply with an authenticated version if credentials are
            # available and the server has requested authentication
            if self._username and self._password and reply.status_code == 401:
                reply = session.get(
                    self._url,
                    timeout=self._timeout,
                    auth=self._create_auth_from_failed_request(
                        reply, self._username, self._password
                    ),
                    headers=self._request_headers(),
                )

            reply.raise_for_status()
            return reply
        except requests.exceptions.RequestException as error:
            raise TemporaryCheckError(error) from error
