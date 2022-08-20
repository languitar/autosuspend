import json

import pytest
from pytest_mock import MockerFixture
import requests.exceptions

from autosuspend.checks import Check, ConfigurationError, TemporaryCheckError
from autosuspend.checks.kodi import Kodi, KodiIdleTime

from . import CheckTest
from .utils import config_section


class TestKodi(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Kodi(name, url="url", timeout=10)

    def test_playing(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": [{"playerid": 0, "type": "audio"}],
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert Kodi("foo", url="url", timeout=10).check() is not None

        mock_reply.json.assert_called_once_with()

    def test_not_playing(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0", "result": []}
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert Kodi("foo", url="url", timeout=10).check() is None

        mock_reply.json.assert_called_once_with()

    def test_playing_suspend_while_paused(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": {"Player.Playing": True},
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert (
            Kodi("foo", url="url", timeout=10, suspend_while_paused=True).check()
            is not None
        )

        mock_reply.json.assert_called_once_with()

    def test_not_playing_suspend_while_paused(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": {"Player.Playing": False},
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert (
            Kodi("foo", url="url", timeout=10, suspend_while_paused=True).check()
            is None
        )

        mock_reply.json.assert_called_once_with()

    def test_assertion_no_result(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0"}
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            Kodi("foo", url="url", timeout=10).check()

    def test_request_error(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "requests.Session.get", side_effect=requests.exceptions.RequestException()
        )

        with pytest.raises(TemporaryCheckError):
            Kodi("foo", url="url", timeout=10).check()

    def test_json_error(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.side_effect = json.JSONDecodeError("test", "test", 42)
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            Kodi("foo", url="url", timeout=10).check()

    def test_create(self) -> None:
        check = Kodi.create(
            "name",
            config_section(
                {
                    "url": "anurl",
                    "timeout": "12",
                }
            ),
        )

        assert check._url.startswith("anurl")
        assert check._timeout == 12
        assert not check._suspend_while_paused

    def test_create_default_url(self) -> None:
        check = Kodi.create("name", config_section())

        assert check._url.split("?")[0] == "http://localhost:8080/jsonrpc"

    def test_create_timeout_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            Kodi.create("name", config_section({"url": "anurl", "timeout": "string"}))

    def test_create_suspend_while_paused(self) -> None:
        check = Kodi.create(
            "name", config_section({"url": "anurl", "suspend_while_paused": "True"})
        )

        assert check._url.startswith("anurl")
        assert check._suspend_while_paused


class TestKodiIdleTime(CheckTest):
    def create_instance(self, name: str) -> Check:
        return KodiIdleTime(name, url="url", timeout=10, idle_time=10)

    def test_create(self) -> None:
        check = KodiIdleTime.create(
            "name", config_section({"url": "anurl", "timeout": "12", "idle_time": "42"})
        )

        assert check._url.startswith("anurl")
        assert check._timeout == 12
        assert check._idle_time == 42

    def test_create_default_url(self) -> None:
        check = KodiIdleTime.create("name", config_section())

        assert check._url.split("?")[0] == "http://localhost:8080/jsonrpc"

    def test_create_timeout_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            KodiIdleTime.create(
                "name", config_section({"url": "anurl", "timeout": "string"})
            )

    def test_create_idle_time_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            KodiIdleTime.create(
                "name", config_section({"url": "anurl", "idle_time": "string"})
            )

    def test_no_result(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0"}
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check()

    def test_result_is_list(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0", "result": []}
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check()

    def test_result_no_entry(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0", "result": {}}
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check()

    def test_result_wrong_entry(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": {"narf": True},
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check()

    def test_active(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": {"System.IdleTime(42)": False},
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert (
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check() is not None
        )

    def test_inactive(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": {"System.IdleTime(42)": True},
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check() is None

    def test_request_error(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "requests.Session.get", side_effect=requests.exceptions.RequestException()
        )

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check()
