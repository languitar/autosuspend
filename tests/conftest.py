from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable

from dbus import Bus
from dbus.proxies import ProxyObject
import dbusmock
from dbusmock.pytest_fixtures import dbusmock_system, PrivateDBus  # noqa: F401
import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Request, Response

from autosuspend.util import systemd as util_systemd


@pytest.fixture()
def serve_file(httpserver: HTTPServer) -> Callable[[Path], str]:
    """Serve a file via HTTP.

    Returns:
        A callable that expected the file path to server. It returns the URL to
        use for accessing the file.
    """

    def serve(the_file: Path) -> str:
        path = f"/{the_file.name}"
        httpserver.expect_request(path).respond_with_data(the_file.read_bytes())
        return httpserver.url_for(path)

    return serve


@pytest.fixture()
def serve_protected(httpserver: HTTPServer) -> Callable[[Path], tuple[str, str, str]]:
    """Serve a file behind basic authentication.

    Returns:
        A callable that accepts the file path to serve. It returns as a tuple
        the URL to use for the file, valid username and password
    """
    realm = "the_realm"
    username = "the_user"
    password = "the_password"  # only for testing

    def serve(the_file: Path) -> tuple[str, str, str]:
        def handler(request: Request) -> Response:
            auth = request.authorization

            if not auth or not (
                auth.username == username and auth.password == password
            ):
                return Response(
                    "Authentication required",
                    401,
                    {"WWW-Authenticate": f"Basic realm={realm}"},
                )

            else:
                return Response(the_file.read_bytes())

        path = f"/{the_file.name}"
        httpserver.expect_request(path).respond_with_handler(handler)
        return (httpserver.url_for(path), username, password)

    return serve


@pytest.fixture()
def logind(
    monkeypatch: Any,
    dbusmock_system: PrivateDBus,  # noqa
) -> Iterable[ProxyObject]:
    pytest.importorskip("dbus")
    pytest.importorskip("gi")

    with dbusmock.SpawnedMock.spawn_with_template("logind") as server:

        def get_bus() -> Bus:
            return dbusmock_system.bustype.get_connection()

        monkeypatch.setattr(util_systemd, "_get_bus", get_bus)

        yield server.obj


@pytest.fixture()
def _logind_dbus_error(
    monkeypatch: Any, dbusmock_system: PrivateDBus  # noqa
) -> Iterable[None]:
    pytest.importorskip("dbus")
    pytest.importorskip("gi")

    with dbusmock.SpawnedMock.spawn_with_template("logind"):

        def get_bus() -> Bus:
            import dbus

            raise dbus.exceptions.ValidationException("Test")

        monkeypatch.setattr(util_systemd, "_get_bus", get_bus)

        yield
