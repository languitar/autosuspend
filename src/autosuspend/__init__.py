#!/usr/bin/env python3
"""A daemon to suspend a system on inactivity."""

import argparse
from collections.abc import Callable, Iterable, Sequence
import configparser
from contextlib import suppress
from datetime import datetime, timedelta, UTC
import functools
from importlib.metadata import version
import logging
import logging.config
from pathlib import Path
import subprocess
import time
from typing import IO

import portalocker

from .checks import Activity, CheckType, ConfigurationError, TemporaryCheckError, Wakeup
from .util import logger_by_class_instance


# pylint: disable=invalid-name
_logger = logging.getLogger("autosuspend")
# pylint: enable=invalid-name


def execute_suspend(
    command: str | Sequence[str],
    wakeup_at: datetime | None,
) -> None:
    """Suspend the system by calling the specified command.

    Args:
        command:
            The command to execute, which will be executed using shell
            execution
        wakeup_at:
            potential next wakeup time. Only informative.
    """
    _logger.info(
        "Suspending using command: %s with next wake up at %s", command, wakeup_at
    )
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError:
        _logger.warning("Unable to execute suspend command: %s", command, exc_info=True)


def notify_suspend(
    command_wakeup_template: str | None,
    command_no_wakeup: str | None,
    wakeup_at: datetime | None,
) -> None:
    """Call a command to notify on suspending.

    Args:
        command_wakeup_template:
            A template for the command to execute in case a wakeup is
            scheduled.
            It will be executed using shell execution.
            The template is processed with string formatting to include
            information on a potentially scheduled wakeup.
            Notifications can be disable by providing ``None`` here.
        command_no_wakeup:
            Command to execute for notification in case no wake up is
            scheduled.
            Will be executed using shell execution.
        wakeup_at:
            if not ``None``, this is the time the system will wake up again
    """

    def safe_exec(command: str) -> None:
        _logger.info("Notifying using command: %s", command)
        try:
            subprocess.check_call(command, shell=True)
        except subprocess.CalledProcessError:
            _logger.warning(
                "Unable to execute notification command: %s", command, exc_info=True
            )

    if wakeup_at and command_wakeup_template:
        command = command_wakeup_template.format(
            timestamp=wakeup_at.timestamp(), iso=wakeup_at.isoformat()
        )
        safe_exec(command)
    elif not wakeup_at and command_no_wakeup:
        safe_exec(command_no_wakeup)
    else:
        _logger.info("No suitable notification command configured.")


def notify_and_suspend(
    suspend_cmd: str | Sequence[str],
    notify_cmd_wakeup_template: str | None,
    notify_cmd_no_wakeup: str | None,
    wakeup_at: datetime | None,
) -> None:
    notify_suspend(notify_cmd_wakeup_template, notify_cmd_no_wakeup, wakeup_at)
    execute_suspend(suspend_cmd, wakeup_at)


def schedule_wakeup(command_template: str, wakeup_at: datetime) -> None:
    command = command_template.format(
        timestamp=wakeup_at.timestamp(), iso=wakeup_at.isoformat()
    )
    _logger.info("Scheduling wakeup using command: %s", command)
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError:
        _logger.warning(
            "Unable to execute wakeup scheduling command: %s", command, exc_info=True
        )


def _safe_execute_activity(check: Activity, logger: logging.Logger) -> str | None:
    try:
        return check.check()
    except TemporaryCheckError:
        logger.warning("Check %s failed. Ignoring...", check, exc_info=True)
        return f"Check {check.name} failed temporarily"


def execute_checks(
    checks: Iterable[Activity], all_checks: bool, logger: logging.Logger
) -> bool:
    """Execute the provided checks sequentially.

    Args:
        checks:
            the checks to execute
        all_checks:
            if ``True``, execute all checks even if a previous one already
            matched.
        logger:
            the logger instance to use

    Return:
        ``True`` if a check matched
    """
    matched = False
    for check in checks:
        logger.debug("Executing check %s", check.name)
        result = _safe_execute_activity(check, logger)
        if result is not None:
            logger.info("Check %s matched. Reason: %s", check.name, result)
            matched = True
            if not all_checks:
                logger.debug("Skipping further checks")
                break
    return matched


def _safe_execute_wakeup(
    check: Wakeup, timestamp: datetime, logger: logging.Logger
) -> datetime | None:
    try:
        return check.check(timestamp)
    except TemporaryCheckError:
        logger.warning("Wakeup %s failed. Ignoring...", check, exc_info=True)
        return None


def execute_wakeups(
    wakeups: Iterable[Wakeup], timestamp: datetime, logger: logging.Logger
) -> datetime | None:
    wakeup_at = None
    for wakeup in wakeups:
        this_at = _safe_execute_wakeup(wakeup, timestamp, logger)

        # sanity checks
        if this_at is None:
            continue
        if this_at <= timestamp:
            logger.warning(
                "Wakeup %s returned a scheduled wakeup at %s, "
                "which is earlier than the current time %s. "
                "Ignoring.",
                wakeup,
                this_at,
                timestamp,
            )
            continue

        # determine the earliest wake up point in time
        wakeup_at = min(this_at, wakeup_at or this_at)

    return wakeup_at


class Processor:
    """Implements the logic for triggering suspension.

    Args:
        activities:
            the activity checks to execute
        wakeups:
            the wakeup checks to execute
        idle_time:
            the required amount of time the system has to be idle before
            suspension is triggered in seconds
        min_sleep_time:
            the minimum time the system has to sleep before it is woken up
            again in seconds.
        wakeup_delta:
            wake up this amount of seconds before the scheduled wake up time.
        sleep_fn:
            a callable that triggers suspension
        wakeup_fn:
            a callable that schedules the wakeup at the specified time in UTC
            seconds
        notify_fn:
            a callable that is called before suspending.
            One argument gives the scheduled wakeup time or ``None``.
        all_activities:
            if ``True``, execute all activity checks even if a previous one
            already matched.
    """

    def __init__(
        self,
        activities: Iterable[Activity],
        wakeups: Iterable[Wakeup],
        idle_time: float,
        min_sleep_time: float,
        wakeup_delta: float,
        sleep_fn: Callable,
        wakeup_fn: Callable[[datetime], None],
        all_activities: bool,
    ) -> None:
        self._logger = logger_by_class_instance(self)
        self._activities = activities
        self._wakeups = wakeups
        self._idle_time = idle_time
        self._min_sleep_time = min_sleep_time
        self._wakeup_delta = wakeup_delta
        self._sleep_fn = sleep_fn
        self._wakeup_fn = wakeup_fn
        self._all_activities = all_activities
        self._idle_since = None  # type: datetime | None

    def _reset_state(self, reason: str) -> None:
        self._logger.info("%s. Resetting state", reason)
        self._idle_since = None

    def _set_idle(self, since: datetime) -> datetime:
        """Set the idle since marker to the given dt if not already set earlier."""
        self._idle_since = min(since, self._idle_since or since)
        return self._idle_since

    def iteration(self, timestamp: datetime, just_woke_up: bool) -> None:
        self._logger.info("Starting new check iteration")

        # exit in case something prevents suspension
        if just_woke_up:
            self._reset_state("Just woke up from suspension.")
            return

        # determine system activity
        active = execute_checks(self._activities, self._all_activities, self._logger)
        self._logger.debug("All activity checks have been executed. Active: %s", active)
        if active:
            self._reset_state("System is active")
            return

        # set idle timestamp if required
        idle_since = self._set_idle(timestamp)
        self._logger.info("System is idle since %s", idle_since)

        # determine if systems is idle long enough
        idle_seconds = (timestamp - idle_since).total_seconds()
        self._logger.debug("Idle seconds: %s", idle_seconds)
        if idle_seconds <= self._idle_time:
            self._logger.info(
                "Desired idle time of %s s not reached yet. Currently idle since %s s",
                self._idle_time,
                idle_seconds,
            )
            return

        self._logger.info("System is idle long enough.")

        # determine potential wake ups
        wakeup_at = execute_wakeups(self._wakeups, timestamp, self._logger)
        if wakeup_at is None:
            self._logger.debug("No automatic wakeup required")
        else:
            self._logger.debug("System wakeup required at %s", wakeup_at)

            # Apply configured wakeup delta
            wakeup_at -= timedelta(seconds=self._wakeup_delta)
            self._logger.debug(
                "With delta applied, system should wake up at %s",
                wakeup_at,
            )

            wakeup_in = wakeup_at - timestamp
            if wakeup_in.total_seconds() < self._min_sleep_time:
                self._logger.info(
                    "Would wake up in %s seconds, which is "
                    "below the minimum amount of %s s. "
                    "Not suspending.",
                    wakeup_in.total_seconds(),
                    self._min_sleep_time,
                )
                return

            # schedule wakeup
            self._logger.info("Scheduling wakeup at %s", wakeup_at)
            self._wakeup_fn(wakeup_at)

        self._reset_state("Going to suspend")
        self._sleep_fn(wakeup_at)


def _continue_looping(run_for: int | None, start_time: datetime) -> bool:
    return (run_for is None) or (
        datetime.now(UTC) < (start_time + timedelta(seconds=run_for))
    )


def _do_loop_iteration(
    processor: Processor,
    woke_up_file: Path,
    lock_file: Path,
    lock_timeout: float,
) -> None:
    try:
        _logger.debug("New iteration, trying to acquire lock")
        with portalocker.Lock(lock_file, timeout=lock_timeout):
            _logger.debug("Acquired lock")

            just_woke_up = woke_up_file.is_file()
            if just_woke_up:
                _logger.debug("Removing woke up file at %s", woke_up_file)
                try:
                    woke_up_file.unlink()
                except FileNotFoundError:
                    _logger.warning("Just woke up file disappeared", exc_info=True)

            processor.iteration(datetime.now(UTC), just_woke_up)

    except portalocker.LockException:
        _logger.warning("Failed to acquire lock, skipping iteration", exc_info=True)


def loop(
    processor: Processor,
    interval: float,
    run_for: int | None,
    woke_up_file: Path,
    lock_file: Path,
    lock_timeout: float,
) -> None:
    """Run the main loop of the daemon.

    Args:
        processor:
            the processor to use for handling the suspension computations
        interval:
            the length of one iteration of the main loop in seconds
        run_for:
            if specified, run the main loop for the specified amount of seconds
            before terminating (approximately)
        woke_up_file:
            path of a file that marks that the system was sleeping since the
            last processing iterations
        lock_file:
            path of a file used for locking modifications to the `woke_up_file`
            to ensure consistency
        lock_timeout:
            time in seconds to wait for acquiring the lock file
    """
    start_time = datetime.now(UTC)
    while _continue_looping(run_for, start_time):
        _do_loop_iteration(processor, woke_up_file, lock_file, lock_timeout)
        time.sleep(interval)


def config_section_string(section: configparser.SectionProxy) -> str:
    data = {k: v if k != "password" else "<redacted>" for k, v in section.items()}
    return f"{data}"


def _determine_check_class_and_module(
    class_name: str, internal_module: str
) -> tuple[str, str]:
    """Determine module and class of a check depending on whether it is internal."""
    if "." in class_name:
        # dot in class name means external class
        import_module, import_class = class_name.rsplit(".", maxsplit=1)
    else:
        # no dot means internal class
        import_module = f"autosuspend.checks.{internal_module}"
        import_class = class_name

    return import_module, import_class


def _determine_check_class_name(name: str, section: configparser.SectionProxy) -> str:
    # if there is an explicit class, use that one with higher priority
    # else, use the legacy method to determine the check name from the section header
    return section.get("class", name)


def _set_up_single_check(
    section: configparser.SectionProxy,
    prefix: str,
    internal_module: str,
    target_class: type[CheckType],
) -> CheckType:
    name = section.name[len(f"{prefix}.") :]

    class_name = _determine_check_class_name(name, section)

    # try to find the required class
    import_module, import_class = _determine_check_class_and_module(
        class_name, internal_module
    )
    _logger.info(
        "Configuring check %s with class %s from module %s "
        "using config parameters %s",
        name,
        import_class,
        import_module,
        config_section_string(section),
    )
    try:
        klass = getattr(
            __import__(import_module, fromlist=[import_class]), import_class
        )
    except AttributeError as error:
        raise ConfigurationError(
            f"Cannot create built-in check named {class_name}: Class does not exist"
        ) from error

    check = klass.create(name, section)
    if not isinstance(check, target_class):
        raise ConfigurationError(
            "Check %s is not a correct %s instance", check, target_class.__name__
        )
    _logger.debug("Created check instance %s with options %s", check, check.options())

    return check


def set_up_checks(
    config: configparser.ConfigParser,
    prefix: str,
    internal_module: str,
    target_class: type[CheckType],
    error_none: bool = False,
) -> list[CheckType]:
    """Set up :py.class:`Check` instances from a given configuration.

    Args:
        config:
            the configuration to use
        prefix:
            The prefix of sections in the configuration file to use for
            creating instances.
        internal_module:
            Name of the submodule of ``autosuspend.checks`` to use for
            discovering internal check classes.
        target_class:
            the base class to check new instance against
        error_none:
            Raise an error if nothing was configured?
    """
    configured_checks = []

    check_section = [s for s in config.sections() if s.startswith(f"{prefix}.")]
    for section_name in check_section:
        section = config[section_name]

        if not section.getboolean("enabled", fallback=False):
            _logger.debug("Skipping disabled check %s", section_name)
            continue

        configured_checks.append(
            _set_up_single_check(section, prefix, internal_module, target_class)
        )

    if not configured_checks and error_none:
        raise ConfigurationError("No checks enabled")

    return configured_checks


def parse_config(config_file: Iterable[str]) -> configparser.ConfigParser:
    """Parse the configuration file.

    Args:
        config_file:
            The file to parse
    """
    _logger.debug("Reading config file %s", config_file)
    config = configparser.ConfigParser(
        interpolation=configparser.ExtendedInterpolation()
    )
    config.read_file(config_file)
    _logger.debug("Parsed config file: %s", config)
    return config


def parse_arguments(args: Sequence[str] | None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        args:
            if specified, use the provided arguments instead of the default
            ones determined via the :module:`sys` module.
    """
    parser = argparse.ArgumentParser(
        description="Automatically suspends a server based on several criteria",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    default_config: IO[str] | None = None
    with suppress(FileNotFoundError, IsADirectoryError, PermissionError):
        # The open file is required after this function finishes inside the argparse
        # result. Therefore, a context manager is not easily usable here.
        default_config = Path("/etc/autosuspend.conf").open("r")  # noqa: SIM115
    parser.add_argument(
        "-c",
        "--config",
        dest="config_file",
        type=argparse.FileType("r"),
        default=default_config,
        required=default_config is None,
        metavar="FILE",
        help="The config file to use",
    )

    logging_group = parser.add_mutually_exclusive_group()
    logging_group.add_argument(
        "-l",
        "--logging",
        type=argparse.FileType("r"),
        default=None,
        metavar="FILE",
        help="Configures the python logging system from the specified "
        "configuration file.",
    )
    logging_group.add_argument(
        "-d",
        "--debug",
        action="store_true",
        default=False,
        help="Configures the logging system to provide full debug output on stdout.",
    )

    subparsers = parser.add_subparsers(title="subcommands", dest="subcommand")
    subparsers.required = True

    parser_version = subparsers.add_parser(
        "version", help="Outputs the program version"
    )
    parser_version.set_defaults(func=main_version)

    parser_daemon = subparsers.add_parser(
        "daemon", help="Execute the continuously operating daemon"
    )
    parser_daemon.set_defaults(func=main_daemon)
    parser_daemon.add_argument(
        "-a",
        "--allchecks",
        dest="all_checks",
        default=False,
        action="store_true",
        help="Execute all checks even if one has already prevented "
        "the system from going to sleep. Useful to debug individual "
        "checks.",
    )
    parser_daemon.add_argument(
        "-r",
        "--runfor",
        dest="run_for",
        type=float,
        default=None,
        metavar="SEC",
        help="If set, run for the specified amount of seconds before exiting "
        "instead of endless execution.",
    )

    parser_hook = subparsers.add_parser(
        "presuspend", help="Hook method to be called before suspending"
    )
    parser_hook.set_defaults(func=main_hook)

    result = parser.parse_args(args)

    _logger.debug("Parsed command line arguments %s", result)

    return result


def configure_logging(config_file: IO | None, debug: bool) -> None:
    """Configure the python :mod:`logging` system.

    Assumes that either a config file is provided, or debugging is enabled.
    Both together are not possible.

    Args:
        config_file:
            a configuration file pointed by a :ref:`file object
            <python:bltin-file-objects>`
        debug:
            if ``True``, enable debug logging
    """
    if config_file:
        try:
            logging.config.fileConfig(config_file)
        except Exception:  # probably ok for main-like function
            # at least configure warnings
            logging.basicConfig(level=logging.WARNING)
            _logger.warning(
                "Unable to configure logging from file %s. "
                "Falling back to warning level.",
                config_file,
                exc_info=True,
            )
    else:
        if debug:
            logging.basicConfig(level=logging.DEBUG)
        else:
            # at least configure warnings
            logging.basicConfig(level=logging.WARNING)


def get_notify_and_suspend_func(config: configparser.ConfigParser) -> Callable:
    return functools.partial(
        notify_and_suspend,
        config.get("general", "suspend_cmd"),
        config.get(
            "general",
            "notify_cmd_wakeup",
            fallback=None,
        ),
        config.get(
            "general",
            "notify_cmd_no_wakeup",
            fallback=None,
        ),
    )


def get_schedule_wakeup_func(
    config: configparser.ConfigParser,
) -> Callable[[datetime], None]:
    return functools.partial(schedule_wakeup, config.get("general", "wakeup_cmd"))


def get_woke_up_file(config: configparser.ConfigParser) -> Path:
    return Path(
        config.get(
            "general", "woke_up_file", fallback="/var/run/autosuspend-just-woke-up"
        )
    )


def get_lock_file(config: configparser.ConfigParser) -> Path:
    return Path(
        config.get("general", "lock_file", fallback="/var/lock/autosuspend.lock")
    )


def get_lock_timeout(config: configparser.ConfigParser) -> float:
    return config.getfloat("general", "lock_timeout", fallback=30.0)


def get_wakeup_delta(config: configparser.ConfigParser) -> float:
    return config.getfloat("general", "wakeup_delta", fallback=30)


def configure_processor(
    args: argparse.Namespace,
    config: configparser.ConfigParser,
    checks: Iterable[Activity],
    wakeups: Iterable[Wakeup],
) -> Processor:
    return Processor(
        checks,
        wakeups,
        config.getfloat("general", "idle_time", fallback=300),
        config.getfloat("general", "min_sleep_time", fallback=1200),
        get_wakeup_delta(config),
        get_notify_and_suspend_func(config),
        get_schedule_wakeup_func(config),
        all_activities=args.all_checks,
    )


def hook(
    wakeups: list[Wakeup],
    wakeup_delta: float,
    wakeup_fn: Callable[[datetime], None],
    woke_up_file: Path,
    lock_file: Path,
    lock_timeout: float,
) -> None:
    """Installs wake ups and notifies the daemon before suspending.

    Args:
        wakeups:
            set of wakeup checks to use for determining the wake up time
        wakeup_delta:
            The amount of time in seconds to wake up before an event
        wakeup_fn:
            function to call with the next wake up time
        woke_up_file:
            location of the file that instructs the daemon that the system just
            woke up
        lock_file:
            path of a file used for locking modifications to the `woke_up_file`
            to ensure consistency
        lock_timeout:
            time in seconds to wait for acquiring the lock file
    """
    _logger.info("Pre-suspend hook starting, trying to acquire lock")
    try:
        with portalocker.Lock(lock_file, timeout=lock_timeout):
            _logger.debug("Hook acquired lock")

            _logger.debug("Hook executing with configured wake ups: %s", wakeups)
            wakeup_at = execute_wakeups(wakeups, datetime.now(UTC), _logger)
            _logger.debug("Hook next wake up at %s", wakeup_at)

            if wakeup_at:
                wakeup_at -= timedelta(seconds=wakeup_delta)
                _logger.info("Scheduling next wake up at %s", wakeup_at)
                wakeup_fn(wakeup_at)
            else:
                _logger.info("No wake up required. Terminating")

            # create the just woke up file
            woke_up_file.touch()
    except portalocker.LockException:
        _logger.warning(
            "Hook unable to acquire lock. Not informing daemon.", exc_info=True
        )


def main_version(
    args: argparse.Namespace, config: configparser.ConfigParser  # noqa: ARG001
) -> None:
    print(version("autosuspend"))  # noqa: T201


def main_hook(
    args: argparse.Namespace, config: configparser.ConfigParser  # noqa: ARG001
) -> None:
    wakeups = set_up_checks(
        config,
        "wakeup",
        "wakeup",
        Wakeup,  # type: ignore # python/mypy#5374
    )
    hook(
        wakeups,
        get_wakeup_delta(config),
        get_schedule_wakeup_func(config),
        get_woke_up_file(config),
        get_lock_file(config),
        get_lock_timeout(config),
    )


def main_daemon(args: argparse.Namespace, config: configparser.ConfigParser) -> None:
    """Run the daemon."""
    checks = set_up_checks(
        config,
        "check",
        "activity",
        Activity,  # type: ignore
        error_none=True,
    )
    wakeups = set_up_checks(
        config,
        "wakeup",
        "wakeup",
        Wakeup,  # type: ignore
    )

    processor = configure_processor(args, config, checks, wakeups)
    loop(
        processor,
        config.getfloat("general", "interval", fallback=60),
        run_for=args.run_for,
        woke_up_file=get_woke_up_file(config),
        lock_file=get_lock_file(config),
        lock_timeout=get_lock_timeout(config),
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run the daemon."""
    args = parse_arguments(argv)

    configure_logging(args.logging, args.debug)

    config = parse_config(args.config_file)

    args.func(args, config)


if __name__ == "__main__":
    main()
