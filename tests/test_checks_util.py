import configparser
from pathlib import Path
from typing import Any, Callable, Optional, Tuple
from unittest.mock import ANY

import pytest
from pytest_httpserver import HTTPServer
from pytest_mock import MockFixture
import requests

from autosuspend.checks import Activity, ConfigurationError, TemporaryCheckError
from autosuspend.checks.util import CommandMixin, NetworkMixin, XPathMixin


class _CommandMixinSub(CommandMixin, Activity):
    def __init__(self, name: str, command: str) -> None:
        Activity.__init__(self, name)
        CommandMixin.__init__(self, command)

    def check(self) -> Optional[str]:
        pass


class TestCommandMixin:
    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string(
            """
            [section]
            command = narf bla
            """
        )
        check: _CommandMixinSub = _CommandMixinSub.create(
            "name",
            parser["section"],
        )  # type: ignore
        assert check._command == "narf bla"

    def test_create_no_command(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string("""[section]""")
        with pytest.raises(ConfigurationError):
            _CommandMixinSub.create("name", parser["section"])


class TestNetworkMixin:
    def test_collect_missing_url(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string("[section]")
        with pytest.raises(ConfigurationError, match=r"^Lacks 'url'.*"):
            NetworkMixin.collect_init_args(parser["section"])

    def test_username_missing(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string(
            """
            [section]
            url=ok
            password=xxx
            """
        )
        with pytest.raises(ConfigurationError, match=r"^Username and.*"):
            NetworkMixin.collect_init_args(parser["section"])

    def test_password_missing(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string(
            """
            [section]
            url=ok
            username=xxx
            """
        )
        with pytest.raises(ConfigurationError, match=r"^Username and.*"):
            NetworkMixin.collect_init_args(parser["section"])

    def test_collect_default_timeout(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string(
            """
            [section]
            url=nourl
            """
        )
        args = NetworkMixin.collect_init_args(parser["section"])
        assert args["timeout"] == 5

    def test_collect_timeout(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string(
            """
            [section]
            url=nourl
            timeout=42
            """
        )
        args = NetworkMixin.collect_init_args(parser["section"])
        assert args["timeout"] == 42

    def test_collect_invalid_timeout(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string(
            """
            [section]
            url=nourl
            timeout=xx
            """
        )
        with pytest.raises(ConfigurationError, match=r"^Configuration error .*"):
            NetworkMixin.collect_init_args(parser["section"])

    def test_request(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        reply = NetworkMixin(
            serve_file(datadir / "xml_with_encoding.xml"),
            5,
        ).request()
        assert reply is not None
        assert reply.status_code == 200

    def test_requests_exception(self, mocker: MockFixture) -> None:
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
        self, datadir: Path, serve_protected: Callable[[Path], Tuple[str, str, str]]
    ) -> None:
        url, username, password = serve_protected(datadir / "data.txt")
        NetworkMixin(url, 5, username=username, password=password).request()

    def test_invalid_authentication(
        self, datadir: Path, serve_protected: Callable[[Path], Tuple[str, str, str]]
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

    def test_content_type(self, mocker: MockFixture) -> None:
        mock_method = mocker.patch("requests.Session.get")

        content_type = "foo/bar"
        NetworkMixin("url", timeout=5, accept=content_type).request()

        mock_method.assert_called_with(
            ANY, timeout=ANY, headers={"Accept": content_type}
        )


class _XPathMixinSub(XPathMixin, Activity):
    def __init__(self, name: str, **kwargs: Any) -> None:
        Activity.__init__(self, name)
        XPathMixin.__init__(self, **kwargs)

    def check(self) -> Optional[str]:
        pass


class TestXPathMixin:
    def test_smoke(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        result = _XPathMixinSub(
            "foo",
            xpath="/b",
            url=serve_file(datadir / "xml_with_encoding.xml"),
            timeout=5,
        ).evaluate()
        assert result is not None
        assert len(result) == 0

    def test_broken_xml(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = b"//broken"
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            _XPathMixinSub("foo", xpath="/b", url="nourl", timeout=5).evaluate()

    def test_xml_with_encoding(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = (
            b'<?xml version="1.0" encoding="ISO-8859-1" ?><root></root>'
        )
        mocker.patch("requests.Session.get", return_value=mock_reply)

        _XPathMixinSub("foo", xpath="/b", url="nourl", timeout=5).evaluate()

    def test_xpath_prevalidation(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string(
            """
            [section]
            xpath=|34/ad
            url=nourl
            """
        )
        with pytest.raises(ConfigurationError, match=r"^Invalid xpath.*"):
            _XPathMixinSub.create("name", parser["section"])

    @pytest.mark.parametrize("entry", ["xpath", "url"])
    def test_missing_config_entry(self, entry: str) -> None:
        parser = configparser.ConfigParser()
        parser.read_string(
            """
            [section]
            xpath=/valid
            url=nourl
            """
        )
        del parser["section"][entry]
        with pytest.raises(ConfigurationError, match=r"^Lacks '" + entry + "'.*"):
            _XPathMixinSub.create("name", parser["section"])

    def test_invalid_config_entry(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string(
            """
            [section]
            xpath=/valid
            timeout=xxx
            url=nourl
            """
        )
        with pytest.raises(ConfigurationError, match=r"^Configuration error .*"):
            _XPathMixinSub.create("name", parser["section"])
