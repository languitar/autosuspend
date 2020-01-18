#!/usr/bin/env python3
"""A daemon to suspend a system on inactivity."""

import argparse
import configparser
import datetime
import functools
import logging
import logging.config
import os
import os.path
import pathlib
import subprocess
import time
from typing import (
    Callable,
    IO,
    Iterable,
    List,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
)

import portalocker

from .checks import Activity, Check, ConfigurationError, TemporaryCheckError, Wakeup
from .util import logger_by_class_instance


# pylint: disable=invalid-name
_logger = logging.getLogger("autosuspend")
# pylint: enable=invalid-name


def execute_suspend(
    command: Union[str, Sequence[str]], wakeup_at: Optional[datetime.datetime],
) -> None:
    """Suspend the system by calling the specified command.

    Args:
        command:
            The command to execute, which will be executed using shell
            execution
        wakeup_at:
            potential next wakeup time. Only informative.
    """
    _logger.info("Suspending using command: %s", command)
    try:
        subprocess.check_call(command, shell=True)  # noqa: S602
    except subprocess.CalledProcessError:
        _logger.warning("Unable to execute suspend command: %s", command, exc_info=True)


def notify_suspend(
    command_wakeup_template: Optional[str],
    command_no_wakeup: Optional[str],
    wakeup_at: Optional[datetime.datetime],
) -> None:
    """Call a command to notify on suspending.

    Args:
        command_no_wakeup_template:
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
            subprocess.check_call(command, shell=True)  # noqa: S602
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
    suspend_cmd: Union[str, Sequence[str]],
    notify_cmd_wakeup_template: Optional[str],
    notify_cmd_no_wakeup: Optional[str],
    wakeup_at: Optional[datetime.datetime],
) -> None:
    notify_suspend(notify_cmd_wakeup_template, notify_cmd_no_wakeup, wakeup_at)
    execute_suspend(suspend_cmd, wakeup_at)


def schedule_wakeup(command_template: str, wakeup_at: datetime.datetime) -> None:
    command = command_template.format(
        timestamp=wakeup_at.timestamp(), iso=wakeup_at.isoformat()
    )
    _logger.info("Scheduling wakeup using command: %s", command)
    try:
        subprocess.check_call(command, shell=True)  # noqa: S602
    except subprocess.CalledProcessError:
        _logger.warning(
            "Unable to execute wakeup scheduling command: %s", command, exc_info=True
        )


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

    Return:
        ``True`` if a check matched
    """
    matched = False
    for check in checks:
        logger.debug("Executing check %s", check.name)
        try:
            result = check.check()
            if result is not None:
                logger.info("Check %s matched. Reason: %s", check.name, result)
                matched = True
                if not all_checks:
                    logger.debug("Skipping further checks")
                    break
        except TemporaryCheckError:
            logger.warning("Check %s failed. Ignoring...", check, exc_info=True)
    return matched


def execute_wakeups(
    wakeups: Iterable[Wakeup], timestamp: datetime.datetime, logger: logging.Logger
) -> Optional[datetime.datetime]:

    wakeup_at = None
    for wakeup in wakeups:
        try:
            this_at = wakeup.check(timestamp)

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

            if wakeup_at is None:
                wakeup_at = this_at
            else:
                wakeup_at = min(this_at, wakeup_at)
        except TemporaryCheckError:
            logger.warning("Wakeup %s failed. Ignoring...", wakeup, exc_info=True)

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
        wakeup_fn: Callable[[datetime.datetime], None],
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
        self._idle_since = None  # type: Optional[datetime.datetime]

    def _reset_state(self, reason: str) -> None:
        self._logger.info("%s. Resetting state", reason)
        self._idle_since = None

    def iteration(self, timestamp: datetime.datetime, just_woke_up: bool) -> None:
        self._logger.info("Starting new check iteration")

        # exit in case something prevents suspension
        if just_woke_up:
            self._reset_state("Just woke up from suspension.")
            return

        # determine system activity
        active = execute_checks(self._activities, self._all_activities, self._logger)
        self._logger.debug(
            "All activity checks have been executed. " "Active: %s", active
        )
        if active:
            self._reset_state("System is active")
            return

        # set idle timestamp if required
        if self._idle_since is None:
            self._idle_since = timestamp

        self._logger.info("System is idle since %s", self._idle_since)

        # determine if systems is idle long enough
        self._logger.debug(
            "Idle seconds: %s", (timestamp - self._idle_since).total_seconds()
        )
        if (timestamp - self._idle_since).total_seconds() > self._idle_time:
            self._logger.info("System is idle long enough.")

            # determine potential wake ups
            wakeup_at = execute_wakeups(self._wakeups, timestamp, self._logger)
            if wakeup_at is not None:
                self._logger.debug("System wakeup required at %s", wakeup_at)
                wakeup_at -= datetime.timedelta(seconds=self._wakeup_delta)
                self._logger.debug(
                    "With delta applied, system should wake up at %s", wakeup_at,
                )
            else:
                self._logger.debug("No automatic wakeup required")

            # idle time would be reached, handle wake up
            if wakeup_at is not None:
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
        else:
            self._logger.info(
                "Desired idle time of %s s not reached yet.", self._idle_time
            )


def loop(
    processor: Processor,
    interval: float,
    run_for: Optional[int],
    woke_up_file: str,
    lock_file: str,
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

    start_time = datetime.datetime.now(datetime.timezone.utc)
    while (run_for is None) or (
        datetime.datetime.now(datetime.timezone.utc)
        < (start_time + datetime.timedelta(seconds=run_for))
    ):

        try:
            _logger.debug("New iteration, trying to acquire lock")
            with portalocker.Lock(lock_file, timeout=lock_timeout):
                _logger.debug("Acquired lock")

                just_woke_up = os.path.isfile(woke_up_file)
                if just_woke_up:
                    _logger.debug("Removing woke up file at %s", woke_up_file)
                    try:
                        os.remove(woke_up_file)
                    except FileNotFoundError:
                        _logger.warning("Just woke up file disappeared", exc_info=True)

                processor.iteration(
                    datetime.datetime.now(datetime.timezone.utc), just_woke_up
                )

        except portalocker.LockException:
            _logger.warning("Failed to acquire lock, skipping iteration", exc_info=True)

        time.sleep(interval)


CheckType = TypeVar("CheckType", bound=Check)


def config_section_string(section: configparser.SectionProxy) -> str:
    data = {k: v if k != "password" else "<redacted>" for k, v in section.items()}
    return f"{data}"


def set_up_checks(
    config: configparser.ConfigParser,
    prefix: str,
    internal_module: str,
    target_class: Type[CheckType],
    error_none: bool = False,
) -> List[CheckType]:
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
    configured_checks = []  # type: List[CheckType]

    check_section = [s for s in config.sections() if s.startswith("{}.".format(prefix))]
    for section in check_section:
        name = section[len("{}.".format(prefix)) :]
        # legacy method to determine the check name from the section header
        class_name = name
        # if there is an explicit class, use that one with higher priority
        if "class" in config[section]:
            class_name = config[section]["class"]
        enabled = config.getboolean(section, "enabled", fallback=False)

        if not enabled:
            _logger.debug("Skipping disabled check {}".format(name))
            continue

        # try to find the required class
        if "." in class_name:
            # dot in class name means external class
            import_module, import_class = class_name.rsplit(".", maxsplit=1)
        else:
            # no dot means internal class
            import_module = "autosuspend.checks.{}".format(internal_module)
            import_class = class_name
        _logger.info(
            "Configuring check %s with class %s from module %s "
            "using config parameters %s",
            name,
            import_class,
            import_module,
            config_section_string(config[section]),
        )
        try:
            klass = getattr(
                __import__(import_module, fromlist=[import_class]), import_class
            )
        except AttributeError as error:
            raise ConfigurationError(
                "Cannot create built-in check named {}: "
                "Class does not exist".format(class_name)
            ) from error

        check = klass.create(name, config[section])
        if not isinstance(check, target_class):
            raise ConfigurationError(
                "Check {} is not a correct {} instance".format(
                    check, target_class.__name__
                )
            )
        _logger.debug(
            "Created check instance {} with options {}".format(check, check.options())
        )
        configured_checks.append(check)

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


def parse_arguments(args: Optional[Sequence[str]]) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        args:
            if specified, use the provided arguments instead of the default
            ones determined via the :module:`sys` module.
    """
    parser = argparse.ArgumentParser(
        description="Automatically suspends a server " "based on several criteria",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    IO  # for making pyflakes happy
    default_config = None  # type: Optional[IO[str]]
    try:
        default_config = open("/etc/autosuspend.conf", "r")
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        pass
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
        help="Configures the logging system to provide full debug output " "on stdout.",
    )

    subparsers = parser.add_subparsers(title="subcommands", dest="subcommand")
    subparsers.required = True

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


def configure_logging(config_file: Optional[IO], debug: bool) -> None:
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
        except Exception:
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
            "general",  # type: ignore # python/typeshed#2093
            "notify_cmd_wakeup",
            fallback=None,
        ),
        config.get(
            "general",  # type: ignore # python/typeshed#2093
            "notify_cmd_no_wakeup",
            fallback=None,
        ),
    )


def get_schedule_wakeup_func(
    config: configparser.ConfigParser,
) -> Callable[[datetime.datetime], None]:
    return functools.partial(schedule_wakeup, config.get("general", "wakeup_cmd"))


def get_woke_up_file(config: configparser.ConfigParser) -> str:
    return config.get(
        "general", "woke_up_file", fallback="/var/run/autosuspend-just-woke-up"
    )


def get_lock_file(config: configparser.ConfigParser) -> str:
    return config.get("general", "lock_file", fallback="/var/lock/autosuspend.lock")


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
    wakeups: List[Wakeup],
    wakeup_delta: float,
    wakeup_fn: Callable[[datetime.datetime], None],
    woke_up_file: str,
    lock_file: str,
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
    _logger.debug("Hook starting, trying to acquire lock")
    try:
        with portalocker.Lock(lock_file, timeout=lock_timeout):
            _logger.debug("Hook acquired lock")

            _logger.debug("Hook executing with configured wake ups: %s", wakeups)
            wakeup_at = execute_wakeups(
                wakeups, datetime.datetime.now(datetime.timezone.utc), _logger
            )
            _logger.debug("Hook next wake up at %s", wakeup_at)

            if wakeup_at:
                wakeup_at -= datetime.timedelta(seconds=wakeup_delta)
                _logger.info("Scheduling next wake up at %s", wakeup_at)
                wakeup_fn(wakeup_at)

            # create the just woke up file
            pathlib.Path(woke_up_file).touch()
    except portalocker.LockException:
        _logger.warning(
            "Hook unable to acquire lock. Not informing daemon.", exc_info=True
        )


def main_hook(args: argparse.Namespace, config: configparser.ConfigParser) -> None:
    wakeups = set_up_checks(
        config, "wakeup", "wakeup", Wakeup,  # type: ignore # python/mypy#5374
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
        config, "wakeup", "wakeup", Wakeup,  # type: ignore
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


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Run the daemon."""
    args = parse_arguments(argv)

    configure_logging(args.logging, args.debug)

    config = parse_config(args.config_file)

    args.func(args, config)


if __name__ == "__main__":
    main()
