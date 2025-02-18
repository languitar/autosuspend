from collections.abc import Callable
from pathlib import Path
from typing import Any

from jsonpath_ng.ext import parse
import pytest
from pytest_mock import MockerFixture

from autosuspend.checks import ConfigurationError, TemporaryCheckError
from autosuspend.checks.json import JsonPath

from . import CheckTest
from .utils import config_section


class TestJsonPath(CheckTest):
    def create_instance(self, name: str) -> JsonPath:
        return JsonPath(
            name=name,
            url="url",
            timeout=5,
            username="userx",
            password="pass",
            jsonpath=parse("b"),
        )

    @staticmethod
    @pytest.fixture
    def json_get_mock(mocker: MockerFixture) -> Any:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"a": {"b": 42, "c": "ignore"}}
        return mocker.patch("requests.Session.get", return_value=mock_reply)

    def test_matching(self, json_get_mock: Any) -> None:
        url = "nourl"
        assert (
            JsonPath("foo", jsonpath=parse("a.b"), url=url, timeout=5).check()
            is not None
        )

        json_get_mock.assert_called_once_with(
            url, timeout=5, headers={"Accept": "application/json"}
        )
        json_get_mock().json.assert_called_once()

    def test_filter_expressions_work(self, json_get_mock: Any) -> None:
        url = "nourl"
        assert (
            JsonPath(
                "foo", jsonpath=parse("$[?(@.c=='ignore')]"), url=url, timeout=5
            ).check()
            is not None
        )

        json_get_mock.assert_called_once_with(
            url, timeout=5, headers={"Accept": "application/json"}
        )
        json_get_mock().json.assert_called_once()

    def test_not_matching(self, json_get_mock: Any) -> None:
        url = "nourl"
        assert (
            JsonPath("foo", jsonpath=parse("not.there"), url=url, timeout=5).check()
            is None
        )

        json_get_mock.assert_called_once_with(
            url, timeout=5, headers={"Accept": "application/json"}
        )
        json_get_mock().json.assert_called_once()

    def test_network_errors_are_passed(
        self, datadir: Path, serve_protected: Callable[[Path], tuple[str, str, str]]
    ) -> None:
        with pytest.raises(TemporaryCheckError):
            JsonPath(
                name="name",
                url=serve_protected(datadir / "data.txt")[0],
                timeout=5,
                username="wrong",
                password="wrong",
                jsonpath=parse("b"),
            ).check()

    def test_not_json(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        with pytest.raises(TemporaryCheckError):
            JsonPath(
                name="name",
                url=serve_file(datadir / "invalid.json"),
                timeout=5,
                jsonpath=parse("b"),
            ).check()

    class TestCreate:
        def test_it_works(self) -> None:
            check: JsonPath = JsonPath.create(
                "name",
                config_section(
                    {
                        "url": "url",
                        "jsonpath": "a.b",
                        "username": "user",
                        "password": "pass",
                        "timeout": "42",
                    }
                ),
            )
            assert check._jsonpath == parse("a.b")
            assert check._url == "url"
            assert check._username == "user"
            assert check._password == "pass"
            assert check._timeout == 42

        def test_raises_on_missing_json_path(self) -> None:
            with pytest.raises(ConfigurationError):
                JsonPath.create(
                    "name",
                    config_section(
                        {
                            "url": "url",
                            "username": "user",
                            "password": "pass",
                            "timeout": "42",
                        }
                    ),
                )

        def test_raises_on_invalid_json_path(self) -> None:
            with pytest.raises(ConfigurationError):
                JsonPath.create(
                    "name",
                    config_section(
                        {
                            "url": "url",
                            "jsonpath": ",.asdfjasdklf",
                            "username": "user",
                            "password": "pass",
                            "timeout": "42",
                        }
                    ),
                )
