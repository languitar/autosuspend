from collections.abc import Callable
from pathlib import Path
from unittest.mock import ANY

import pytest
from pytest_httpserver import HTTPServer
from pytest_mock import MockerFixture
import requests

from autosuspend.checks import ConfigurationError, TemporaryCheckError
from autosuspend.checks.util import NetworkMixin

from .utils import config_section


class TestNetworkMixin:
    def test_collect_missing_url(self) -> None:
        with pytest.raises(ConfigurationError, match=r"^Lacks 'url'.*"):
            NetworkMixin.collect_init_args(config_section())

    def test_username_missing(self) -> None:
        with pytest.raises(ConfigurationError, match=r"^Username and.*"):
            NetworkMixin.collect_init_args(
                config_section({"url": "required", "password": "lacks username"})
            )

    def test_password_missing(self) -> None:
        with pytest.raises(ConfigurationError, match=r"^Username and.*"):
            NetworkMixin.collect_init_args(
                config_section({"url": "required", "username": "lacks password"})
            )

    def test_collect_default_timeout(self) -> None:
        args = NetworkMixin.collect_init_args(config_section({"url": "required"}))
        assert args["timeout"] == 5

    def test_collect_timeout(self) -> None:
        args = NetworkMixin.collect_init_args(
            config_section({"url": "required", "timeout": "42"})
        )
        assert args["timeout"] == 42

    def test_collect_invalid_timeout(self) -> None:
        with pytest.raises(ConfigurationError, match=r"^Configuration error .*"):
            NetworkMixin.collect_init_args(
                config_section({"url": "required", "timeout": "xx"})
            )

    def test_request(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        reply = NetworkMixin(
            serve_file(datadir / "xml_with_encoding.xml"),
            5,
        ).request()
        assert reply is not None
        assert reply.status_code == 200

    def test_requests_exception(self, mocker: MockerFixture) -> None:
        mock_method = mocker.patch("requests.Session.get")
        mock_method.side_effect = requests.exceptions.ReadTimeout()

        with pytest.raises(TemporaryCheckError):
            NetworkMixin("url", timeout=5).request()

    def test_smoke(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        response = NetworkMixin(serve_file(datadir / "data.txt"), timeout=5).request()
        assert response is not None
        assert response.text == "iamhere\n"

    def test_exception_404(self, httpserver: HTTPServer) -> None:
        with pytest.raises(TemporaryCheckError):
            NetworkMixin(httpserver.url_for("/does/not/exist"), timeout=5).request()

    def test_authentication(
        self, datadir: Path, serve_protected: Callable[[Path], tuple[str, str, str]]
    ) -> None:
        url, username, password = serve_protected(datadir / "data.txt")
        NetworkMixin(url, 5, username=username, password=password).request()

    def test_invalid_authentication(
        self, datadir: Path, serve_protected: Callable[[Path], tuple[str, str, str]]
    ) -> None:
        with pytest.raises(TemporaryCheckError):
            NetworkMixin(
                serve_protected(datadir / "data.txt")[0],
                5,
                username="userx",
                password="pass",
            ).request()

    def test_file_url(self) -> None:
        NetworkMixin("file://" + __file__, 5).request()

    def test_content_type(self, mocker: MockerFixture) -> None:
        mock_method = mocker.patch("requests.Session.get")

        content_type = "foo/bar"
        NetworkMixin("url", timeout=5, accept=content_type).request()

        mock_method.assert_called_with(
            ANY, timeout=ANY, headers={"Accept": content_type}
        )
