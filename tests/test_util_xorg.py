import logging
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from autosuspend.util.xorg import (
    list_sessions_logind,
    list_sessions_sockets,
    XorgSession,
)


class TestListSessionsSockets:
    def test_empty(self, tmp_path: Path) -> None:
        assert list_sessions_sockets(tmp_path) == []

    @pytest.mark.parametrize("number", [0, 10, 1024])
    def test_extracts_valid_sockets(self, tmp_path: Path, number: int) -> None:
        session_sock = tmp_path / f"X{number}"
        session_sock.touch()

        assert list_sessions_sockets(tmp_path) == [
            XorgSession(number, session_sock.owner())
        ]

    @pytest.mark.parametrize("invalid_number", ["", "string", "  "])
    def test_ignores_and_warns_on_invalid_numbers(
        self,
        tmp_path: Path,
        invalid_number: str,
        caplog: Any,
    ) -> None:
        (tmp_path / f"X{invalid_number}").touch()

        with caplog.at_level(logging.WARNING):
            assert list_sessions_sockets(tmp_path) == []
            assert caplog.records != []

    def test_ignores_and_warns_on_unknown_users(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        caplog: Any,
    ) -> None:
        (tmp_path / "X0").touch()
        mocker.patch("pathlib.Path.owner").side_effect = KeyError()

        with caplog.at_level(logging.WARNING):
            assert list_sessions_sockets(tmp_path) == []
            assert caplog.records != []

    def test_ignores_other_files(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "asdf").touch()

        assert list_sessions_sockets(tmp_path) == []

    def test_returns_multiple(self, tmp_path: Path) -> None:
        (tmp_path / "X0").touch()
        (tmp_path / "X1").touch()

        assert len(list_sessions_sockets(tmp_path)) == 2


_LIST_LOGIND_SESSIONS_TO_PATCH = "autosuspend.util.xorg.list_logind_sessions"


class TestListSessionsLogind:
    def test_extracts_valid_sessions(self, mocker: MockerFixture) -> None:
        username = "test_user"
        display = 42
        mocker.patch(_LIST_LOGIND_SESSIONS_TO_PATCH).return_value = [
            ("id", {"Name": username, "Display": f":{display}"})
        ]

        assert list_sessions_logind() == [XorgSession(display, username)]

    def test_ignores_sessions_with_missing_properties(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch(_LIST_LOGIND_SESSIONS_TO_PATCH).return_value = [
            ("id", {"Name": "someuser"}),
            ("id", {"Display": ":42"}),
        ]

        assert list_sessions_logind() == []

    def test_ignores_and_warns_on_invalid_display_numbers(
        self,
        mocker: MockerFixture,
        caplog: Any,
    ) -> None:
        mocker.patch(_LIST_LOGIND_SESSIONS_TO_PATCH).return_value = [
            ("id", {"Name": "someuser", "Display": "XXX"}),
        ]

        with caplog.at_level(logging.WARNING):
            assert list_sessions_logind() == []
            assert caplog.records != []
