import subprocess
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from autosuspend.checks import Check, SevereCheckError, TemporaryCheckError
from autosuspend.checks.smb import Smb

from . import CheckTest


class TestSmb(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Smb(name)

    def test_no_connections(self, datadir: Path, mocker: MockerFixture) -> None:
        mocker.patch("subprocess.check_output").return_value = (
            datadir / "smbstatus_no_connections"
        ).read_bytes()

        assert Smb("foo").check() is None

    def test_with_connections(self, datadir: Path, mocker: MockerFixture) -> None:
        mocker.patch("subprocess.check_output").return_value = (
            datadir / "smbstatus_with_connections"
        ).read_bytes()

        res = Smb("foo").check()
        assert res is not None
        assert len(res.splitlines()) == 3

    def test_call_error(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "subprocess.check_output",
            side_effect=subprocess.CalledProcessError(2, "cmd"),
        )

        with pytest.raises(TemporaryCheckError):
            Smb("foo").check()

    def test_missing_executable(self, mocker: MockerFixture) -> None:
        mocker.patch("subprocess.check_output", side_effect=FileNotFoundError)

        with pytest.raises(SevereCheckError):
            Smb("foo").check()

    def test_create(self) -> None:
        assert isinstance(Smb.create("name", None), Smb)
