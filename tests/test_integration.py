import datetime
import logging
import os
import os.path
from pathlib import Path
from typing import Any, Iterable

from freezegun import freeze_time
import pytest
from pytest_mock import MockFixture

import autosuspend


pytestmark = pytest.mark.integration


ROOT = os.path.dirname(os.path.realpath(__file__))

SUSPENSION_FILE = "would_suspend"
SCHEDULED_FILE = "wakeup_at"
WOKE_UP_FILE = "test-woke-up"
LOCK_FILE = "test-woke-up.lock"
NOTIFY_FILE = "notify"


def configure_config(config: str, datadir: Path, tmp_path: Path) -> Path:
    out_path = tmp_path / config
    with out_path.open("w") as out_config:
        out_config.write(
            (datadir / config).read_text().replace("@TMPDIR@", str(tmp_path)),
        )
    return out_path


@pytest.fixture()
def rapid_sleep(mocker: MockFixture) -> Iterable:
    with freeze_time() as frozen_time:
        sleep_mock = mocker.patch("time.sleep")
        sleep_mock.side_effect = lambda seconds: frozen_time.tick(
            datetime.timedelta(seconds=seconds)
        )
        yield frozen_time


def test_no_suspend_if_matching(
    datadir: Path, tmp_path: Path, rapid_sleep: Any
) -> None:
    autosuspend.main(
        [
            "-c",
            str(configure_config("dont_suspend.conf", datadir, tmp_path)),
            "-d",
            "daemon",
            "-r",
            "10",
        ]
    )

    assert not (tmp_path / SUSPENSION_FILE).exists()


def test_suspend(tmp_path: Path, datadir: Path, rapid_sleep: Any) -> None:
    autosuspend.main(
        [
            "-c",
            str(configure_config("would_suspend.conf", datadir, tmp_path)),
            "-d",
            "daemon",
            "-r",
            "10",
        ]
    )

    assert (tmp_path / SUSPENSION_FILE).exists()


def test_wakeup_scheduled(tmp_path: Path, datadir: Path, rapid_sleep: Any) -> None:
    # configure when to wake up
    now = datetime.datetime.now(datetime.timezone.utc)
    wakeup_at = now + datetime.timedelta(hours=4)
    (tmp_path / "wakeup_time").write_text(str(wakeup_at.timestamp()))

    autosuspend.main(
        [
            "-c",
            str(configure_config("would_schedule.conf", datadir, tmp_path)),
            "-d",
            "daemon",
            "-r",
            "10",
        ]
    )

    assert (tmp_path / SUSPENSION_FILE).exists()
    assert (tmp_path / SCHEDULED_FILE).exists()
    assert int((tmp_path / SCHEDULED_FILE).read_text()) == int(
        round((wakeup_at - datetime.timedelta(seconds=30)).timestamp())
    )


def test_woke_up_file_removed(tmp_path: Path, datadir: Path, rapid_sleep: Any) -> None:
    (tmp_path / WOKE_UP_FILE).touch()
    autosuspend.main(
        [
            "-c",
            str(configure_config("dont_suspend.conf", datadir, tmp_path)),
            "-d",
            "daemon",
            "-r",
            "5",
        ]
    )
    assert not (tmp_path / WOKE_UP_FILE).exists()


def test_notify_call(tmp_path: Path, datadir: Path, rapid_sleep: Any) -> None:
    autosuspend.main(
        [
            "-c",
            str(configure_config("notify.conf", datadir, tmp_path)),
            "-d",
            "daemon",
            "-r",
            "10",
        ]
    )

    assert (tmp_path / SUSPENSION_FILE).exists()
    assert (tmp_path / NOTIFY_FILE).exists()
    assert len((tmp_path / NOTIFY_FILE).read_text()) == 0


def test_notify_call_wakeup(tmp_path: Path, datadir: Path, rapid_sleep: Any) -> None:
    # configure when to wake up
    now = datetime.datetime.now(datetime.timezone.utc)
    wakeup_at = now + datetime.timedelta(hours=4)
    (tmp_path / "wakeup_time").write_text(str(wakeup_at.timestamp()))

    autosuspend.main(
        [
            "-c",
            str(configure_config("notify_wakeup.conf", datadir, tmp_path)),
            "-d",
            "daemon",
            "-r",
            "10",
        ]
    )

    assert (tmp_path / SUSPENSION_FILE).exists()
    assert (tmp_path / NOTIFY_FILE).exists()
    assert int((tmp_path / NOTIFY_FILE).read_text()) == int(
        round((wakeup_at - datetime.timedelta(seconds=10)).timestamp())
    )


def test_error_no_checks_configured(tmp_path: Path, datadir: Path) -> None:
    with pytest.raises(autosuspend.ConfigurationError):
        autosuspend.main(
            [
                "-c",
                str(configure_config("no_checks.conf", datadir, tmp_path)),
                "-d",
                "daemon",
                "-r",
                "10",
            ]
        )


def test_temporary_errors_logged(
    tmp_path: Path, datadir: Path, rapid_sleep: Path, caplog: Any
) -> None:
    autosuspend.main(
        [
            "-c",
            str(configure_config("temporary_error.conf", datadir, tmp_path)),
            "-d",
            "daemon",
            "-r",
            "10",
        ]
    )

    warnings = [
        r
        for r in caplog.record_tuples
        if r[1] == logging.WARNING and "XPath" in r[2] and "failed" in r[2]
    ]

    assert len(warnings) > 0


def test_loop_defaults(tmp_path: Path, datadir: Path, mocker: MockFixture) -> None:
    loop = mocker.patch("autosuspend.loop")
    loop.side_effect = StopIteration
    with pytest.raises(StopIteration):
        autosuspend.main(
            [
                "-c",
                str(configure_config("minimal.conf", datadir, tmp_path)),
                "-d",
                "daemon",
                "-r",
                "10",
            ]
        )
    args, kwargs = loop.call_args
    assert args[1] == 60
    assert kwargs["run_for"] == 10
    assert kwargs["woke_up_file"] == ("/var/run/autosuspend-just-woke-up")


def test_hook_success(tmp_path: Path, datadir: Path) -> None:
    autosuspend.main(
        [
            "-c",
            str(configure_config("would_suspend.conf", datadir, tmp_path)),
            "-d",
            "presuspend",
        ]
    )

    assert (tmp_path / WOKE_UP_FILE).exists()


def test_hook_call_wakeup(tmp_path: Path, datadir: Path) -> None:
    # configure when to wake up
    now = datetime.datetime.now(datetime.timezone.utc)
    wakeup_at = now + datetime.timedelta(hours=4)
    (tmp_path / "wakeup_time").write_text(str(wakeup_at.timestamp()))

    autosuspend.main(
        [
            "-c",
            str(configure_config("would_schedule.conf", datadir, tmp_path)),
            "-d",
            "presuspend",
        ]
    )

    assert (tmp_path / SCHEDULED_FILE).exists()
    assert int((tmp_path / SCHEDULED_FILE).read_text()) == int(
        round((wakeup_at - datetime.timedelta(seconds=30)).timestamp())
    )
