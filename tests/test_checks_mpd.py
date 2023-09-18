from typing import Any

import mpd
import pytest
from pytest_mock import MockerFixture

from autosuspend.checks import Check, ConfigurationError, TemporaryCheckError
from autosuspend.checks.mpd import Mpd

from . import CheckTest
from .utils import config_section


class TestMpd(CheckTest):
    def create_instance(self, name: str) -> Check:
        # concrete values are never used in the tests
        return Mpd(name, None, None, None)  # type: ignore

    def test_playing(self, monkeypatch: Any) -> None:
        check = Mpd("test", None, None, None)  # type: ignore

        def get_state() -> dict:
            return {"state": "play"}

        monkeypatch.setattr(check, "_get_state", get_state)

        assert check.check() is not None

    def test_not_playing(self, monkeypatch: Any) -> None:
        check = Mpd("test", None, None, None)  # type: ignore

        def get_state() -> dict:
            return {"state": "pause"}

        monkeypatch.setattr(check, "_get_state", get_state)

        assert check.check() is None

    def test_correct_mpd_interaction(self, mocker: MockerFixture) -> None:
        mock_instance = mocker.MagicMock(spec=mpd.MPDClient)
        mock_instance.status.return_value = {"state": "play"}
        timeout_property = mocker.PropertyMock()
        type(mock_instance).timeout = timeout_property
        mock = mocker.patch("autosuspend.checks.mpd.MPDClient")
        mock.return_value = mock_instance

        host = "foo"
        port = 42
        timeout = 17

        assert Mpd("name", host, port, timeout).check() is not None

        timeout_property.assert_called_once_with(timeout)
        mock_instance.connect.assert_called_once_with(host, port)
        mock_instance.status.assert_called_once_with()
        mock_instance.close.assert_called_once_with()
        mock_instance.disconnect.assert_called_once_with()

    @pytest.mark.parametrize("exception_type", [ConnectionError, mpd.ConnectionError])
    def test_handle_connection_errors(self, exception_type: type) -> None:
        check = Mpd("test", None, None, None)  # type: ignore

        def _get_state() -> dict:
            raise exception_type()

        # https://github.com/python/mypy/issues/2427
        check._get_state = _get_state  # type: ignore

        with pytest.raises(TemporaryCheckError):
            check.check()

    def test_create(self) -> None:
        check = Mpd.create(
            "name",
            config_section(
                {
                    "host": "host",
                    "port": "1234",
                    "timeout": "12",
                }
            ),
        )

        assert check._host == "host"
        assert check._port == 1234
        assert check._timeout == 12

    def test_create_port_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            Mpd.create(
                "name",
                config_section(
                    {
                        "host": "host",
                        "port": "string",
                        "timeout": "12",
                    }
                ),
            )

    def test_create_timeout_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            Mpd.create(
                "name",
                config_section(
                    {
                        "host": "host",
                        "port": "10",
                        "timeout": "string",
                    }
                ),
            )
