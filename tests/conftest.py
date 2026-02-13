import textwrap
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import dbusmock
import pytest
from dbus import Bus
from dbus.proxies import ProxyObject
from dbusmock.pytest_fixtures import PrivateDBus, dbusmock_system  # noqa: F401
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Request, Response

from autosuspend.util import systemd as util_systemd


@pytest.fixture
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


@pytest.fixture
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


@pytest.fixture
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

        # Add inhibitor support to the logind mock
        server.obj.AddMethods(
            "org.freedesktop.login1.Manager",
            [
                (
                    "ListInhibitors",
                    "",
                    "a(ssssuu)",
                    textwrap.dedent(
                        """
                        if not hasattr(self, '_inhibitors'):
                            self._inhibitors = []
                        ret = self._inhibitors
                        """,
                    ),
                ),
                (
                    "AddInhibitor",
                    "ssssuu",
                    "",
                    textwrap.dedent(
                        """
                        if not hasattr(self, '_inhibitors'):
                            self._inhibitors = []
                        self._inhibitors.append((args[0], args[1], args[2], args[3], args[4], args[5]))
                        """,
                    ),
                ),
                (
                    "RemoveInhibitor",
                    "uu",
                    "",
                    textwrap.dedent(
                        """
                        if not hasattr(self, '_inhibitors'):
                            self._inhibitors = []
                        uid_arg = args[0]
                        pid_arg = args[1]
                        new_inhibitors = []
                        for w, who, why, m, uid, pid in self._inhibitors:
                            if not (uid == uid_arg and pid == pid_arg):
                                new_inhibitors.append((w, who, why, m, uid, pid))
                        self._inhibitors = new_inhibitors
                        """,
                    ),
                ),
            ],
        )

        yield server.obj


@pytest.fixture
def _logind_dbus_error(
    monkeypatch: Any,
    dbusmock_system: PrivateDBus,  # noqa
) -> Iterable[None]:
    pytest.importorskip("dbus")
    pytest.importorskip("gi")

    with dbusmock.SpawnedMock.spawn_with_template("logind"):

        def get_bus() -> Bus:
            import dbus

            raise dbus.exceptions.ValidationException("Test")

        monkeypatch.setattr(util_systemd, "_get_bus", get_bus)

        yield
