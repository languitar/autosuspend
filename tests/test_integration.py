import datetime
import logging
import os
import os.path

from freezegun import freeze_time
import pytest

import autosuspend


pytestmark = pytest.mark.integration


ROOT = os.path.dirname(os.path.realpath(__file__))

SUSPENSION_FILE = "would_suspend"
SCHEDULED_FILE = "wakeup_at"
WOKE_UP_FILE = "test-woke-up"
LOCK_FILE = "test-woke-up.lock"
NOTIFY_FILE = "notify"


def configure_config(config, datadir, tmpdir):
    out_path = tmpdir.join(config)
    with out_path.open("w") as out_config:
        out_config.write(
            (datadir / config).read_text().replace("@TMPDIR@", tmpdir.strpath),
        )
    return out_path


@pytest.fixture
def rapid_sleep(mocker):
    with freeze_time() as frozen_time:
        sleep_mock = mocker.patch("time.sleep")
        sleep_mock.side_effect = lambda seconds: frozen_time.tick(
            datetime.timedelta(seconds=seconds)
        )
        yield frozen_time


def test_no_suspend_if_matching(datadir, tmpdir, rapid_sleep) -> None:
    autosuspend.main(
        [
            "-c",
            configure_config("dont_suspend.conf", datadir, tmpdir).strpath,
            "-d",
            "daemon",
            "-r",
            "10",
        ]
    )

    assert not tmpdir.join(SUSPENSION_FILE).check()


def test_suspend(tmpdir, datadir, rapid_sleep) -> None:
    autosuspend.main(
        [
            "-c",
            configure_config("would_suspend.conf", datadir, tmpdir).strpath,
            "-d",
            "daemon",
            "-r",
            "10",
        ]
    )

    assert tmpdir.join(SUSPENSION_FILE).check()


def test_wakeup_scheduled(tmpdir, datadir, rapid_sleep) -> None:
    # configure when to wake up
    now = datetime.datetime.now(datetime.timezone.utc)
    wakeup_at = now + datetime.timedelta(hours=4)
    with tmpdir.join("wakeup_time").open("w") as out:
        out.write(str(wakeup_at.timestamp()))

    autosuspend.main(
        [
            "-c",
            configure_config("would_schedule.conf", datadir, tmpdir).strpath,
            "-d",
            "daemon",
            "-r",
            "10",
        ]
    )

    assert tmpdir.join(SUSPENSION_FILE).check()
    assert tmpdir.join(SCHEDULED_FILE).check()
    assert int(tmpdir.join(SCHEDULED_FILE).read()) == int(
        round((wakeup_at - datetime.timedelta(seconds=30)).timestamp())
    )


def test_woke_up_file_removed(tmpdir, datadir, rapid_sleep) -> None:
    tmpdir.join(WOKE_UP_FILE).ensure()
    autosuspend.main(
        [
            "-c",
            configure_config("dont_suspend.conf", datadir, tmpdir).strpath,
            "-d",
            "daemon",
            "-r",
            "5",
        ]
    )
    assert not tmpdir.join(WOKE_UP_FILE).check()


def test_notify_call(tmpdir, datadir, rapid_sleep) -> None:
    autosuspend.main(
        [
            "-c",
            configure_config("notify.conf", datadir, tmpdir).strpath,
            "-d",
            "daemon",
            "-r",
            "10",
        ]
    )

    assert tmpdir.join(SUSPENSION_FILE).check()
    assert tmpdir.join(NOTIFY_FILE).check()
    assert len(tmpdir.join(NOTIFY_FILE).read()) == 0


def test_notify_call_wakeup(tmpdir, datadir, rapid_sleep) -> None:
    # configure when to wake up
    now = datetime.datetime.now(datetime.timezone.utc)
    wakeup_at = now + datetime.timedelta(hours=4)
    with tmpdir.join("wakeup_time").open("w") as out:
        out.write(str(wakeup_at.timestamp()))

    autosuspend.main(
        [
            "-c",
            configure_config("notify_wakeup.conf", datadir, tmpdir).strpath,
            "-d",
            "daemon",
            "-r",
            "10",
        ]
    )

    assert tmpdir.join(SUSPENSION_FILE).check()
    assert tmpdir.join(NOTIFY_FILE).check()
    assert int(tmpdir.join(NOTIFY_FILE).read()) == int(
        round((wakeup_at - datetime.timedelta(seconds=10)).timestamp())
    )


def test_error_no_checks_configured(tmpdir, datadir) -> None:
    with pytest.raises(autosuspend.ConfigurationError):
        autosuspend.main(
            [
                "-c",
                configure_config("no_checks.conf", datadir, tmpdir).strpath,
                "-d",
                "daemon",
                "-r",
                "10",
            ]
        )


def test_temporary_errors_logged(tmpdir, datadir, rapid_sleep, caplog) -> None:
    autosuspend.main(
        [
            "-c",
            configure_config("temporary_error.conf", datadir, tmpdir).strpath,
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


def test_loop_defaults(tmpdir, datadir, mocker) -> None:
    loop = mocker.patch("autosuspend.loop")
    loop.side_effect = StopIteration
    with pytest.raises(StopIteration):
        autosuspend.main(
            [
                "-c",
                configure_config("minimal.conf", datadir, tmpdir).strpath,
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


def test_hook_success(tmpdir, datadir):
    autosuspend.main(
        [
            "-c",
            configure_config("would_suspend.conf", datadir, tmpdir).strpath,
            "-d",
            "presuspend",
        ]
    )

    assert tmpdir.join(WOKE_UP_FILE).check()


def test_hook_call_wakeup(tmpdir, datadir):
    # configure when to wake up
    now = datetime.datetime.now(datetime.timezone.utc)
    wakeup_at = now + datetime.timedelta(hours=4)
    with tmpdir.join("wakeup_time").open("w") as out:
        out.write(str(wakeup_at.timestamp()))

    autosuspend.main(
        [
            "-c",
            configure_config("would_schedule.conf", datadir, tmpdir).strpath,
            "-d",
            "presuspend",
        ]
    )

    assert tmpdir.join(SCHEDULED_FILE).check()
    assert int(tmpdir.join(SCHEDULED_FILE).read()) == int(
        round((wakeup_at - datetime.timedelta(seconds=30)).timestamp())
    )
