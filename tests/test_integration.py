import logging
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from freezegun import freeze_time
from pytest_mock import MockerFixture

import autosuspend

pytestmark = pytest.mark.integration


SUSPENSION_FILE = "would_suspend"
SCHEDULED_FILE = "wakeup_at"
NOTIFY_FILE = "notify"


def configure_config(config: str, datadir: Path, tmp_path: Path) -> Path:
    out_path = tmp_path / config
    with out_path.open("w") as out_config:
        out_config.write(
            (datadir / config).read_text().replace("@TMPDIR@", str(tmp_path)),
        )
    return out_path


@pytest.fixture
def mock_time(mocker: MockerFixture) -> Iterable[Any]:
    """Mock time.sleep to work with freezegun."""
    with freeze_time() as frozen_time:
        sleep_mock = mocker.patch("time.sleep")
        sleep_mock.side_effect = lambda seconds: frozen_time.tick(
            timedelta(seconds=seconds)
        )
        yield frozen_time


@pytest.fixture
def mock_dbus_signals(mocker: MockerFixture) -> None:
    """Mock DBus to simulate PrepareForSleep signals on subprocess calls."""
    signal_handler = None
    in_signal_handler = [False]

    def mock_add_signal_receiver(handler: Any, **kwargs: Any) -> None:
        nonlocal signal_handler
        if kwargs.get("signal_name") == "PrepareForSleep":
            signal_handler = handler

    mock_bus = mocker.MagicMock()
    mock_bus.add_signal_receiver.side_effect = mock_add_signal_receiver
    mocker.patch("autosuspend.dbus.SystemBus", return_value=mock_bus)

    # Mock subprocess to trigger PrepareForSleep signal on suspend commands
    original_check_call = subprocess.check_call

    def mock_check_call(cmd: Any, *args: Any, **kwargs: Any) -> None:
        # Trigger PrepareForSleep(True) when sleep_fn calls subprocess
        if signal_handler and not in_signal_handler[0]:
            in_signal_handler[0] = True
            try:
                signal_handler(True)
            finally:
                in_signal_handler[0] = False
        # Don't actually call systemctl suspend in tests
        if not (isinstance(cmd, str) and "systemctl" in cmd) and not (
            isinstance(cmd, list) and any("systemctl" in str(c) for c in cmd)
        ):
            original_check_call(cmd, *args, **kwargs)

    mocker.patch("subprocess.check_call", side_effect=mock_check_call)


@pytest.fixture
def mock_glib_loop(mocker: MockerFixture, mock_time: Any) -> None:
    """Mock GLib event loop to run synchronously with frozen time."""
    callbacks = []

    def mock_timeout_add_seconds(interval: int, callback: Any, *args: Any) -> int:
        callbacks.append((interval, callback, args))
        return len(callbacks)

    def mock_idle_add(callback: Any, *args: Any, **kwargs: Any) -> int:
        callback(*args, **kwargs)
        return 1

    mocker.patch(
        "autosuspend.GLib.timeout_add_seconds", side_effect=mock_timeout_add_seconds
    )
    mocker.patch("autosuspend.GLib.idle_add", side_effect=mock_idle_add)

    class MockMainLoop:
        def __init__(self) -> None:
            self.running = False

        def run(self) -> None:
            self.running = True
            while self.running and callbacks:
                interval, callback, args = callbacks[0]
                mock_time.tick(timedelta(seconds=interval))
                should_continue = callback(*args)
                if not should_continue:
                    break

        def quit(self) -> None:
            self.running = False

    mocker.patch("autosuspend.GLib.MainLoop", return_value=MockMainLoop())


@pytest.fixture
def daemon_environment(
    mock_time: Any,
    mock_dbus_signals: None,
    mock_glib_loop: None,
) -> None:
    """Complete test environment for daemon integration tests.

    Combines time mocking, DBus signal simulation, and GLib event loop
    mocking for end-to-end daemon testing.

    Args are fixture dependencies that must be activated.
    """
    # All work done by dependent fixtures
    _ = (mock_time, mock_dbus_signals, mock_glib_loop)


@pytest.mark.usefixtures("daemon_environment")
def test_no_suspend_if_matching(datadir: Path, tmp_path: Path) -> None:
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


@pytest.mark.usefixtures("daemon_environment")
def test_suspend(tmp_path: Path, datadir: Path) -> None:
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


@pytest.mark.usefixtures("daemon_environment")
def test_wakeup_scheduled(tmp_path: Path, datadir: Path) -> None:
    # configure when to wake up
    now = datetime.now(UTC)
    wakeup_at = now + timedelta(hours=4)
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
    assert int((tmp_path / SCHEDULED_FILE).read_text()) == round(
        (wakeup_at - timedelta(seconds=30)).timestamp()
    )


@pytest.mark.usefixtures("daemon_environment")
def test_notify_call(tmp_path: Path, datadir: Path) -> None:
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


@pytest.mark.usefixtures("daemon_environment")
def test_notify_call_wakeup(tmp_path: Path, datadir: Path) -> None:
    # configure when to wake up
    now = datetime.now(UTC)
    wakeup_at = now + timedelta(hours=4)
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
    assert int((tmp_path / NOTIFY_FILE).read_text()) == round(
        (wakeup_at - timedelta(seconds=10)).timestamp()
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


@pytest.mark.usefixtures("daemon_environment")
def test_temporary_errors_logged(tmp_path: Path, datadir: Path, caplog: Any) -> None:
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


def test_loop_defaults(tmp_path: Path, datadir: Path, mocker: MockerFixture) -> None:
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
    # check arguments passed to loop()
    assert args[1] == 60  # interval
    assert kwargs["run_for"] == 10


def test_version(tmp_path: Path, datadir: Path) -> None:
    autosuspend.main(
        [
            "-c",
            str(configure_config("would_schedule.conf", datadir, tmp_path)),
            "version",
        ]
    )
