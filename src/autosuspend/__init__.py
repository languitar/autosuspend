#!/usr/bin/env python3
"""A daemon to suspend a system on inactivity."""

import argparse
import configparser
import functools
import importlib
import inspect
import logging
import logging.config
import math
import subprocess
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

from .checks import Activity, CheckType, ConfigurationError, TemporaryCheckError, Wakeup
from .config import GENERAL_PARAMETERS, ConfigSchema
from .util import logger_by_class_instance
from .util.systemd import LogindDBusException, has_inhibit_lock

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

    def schedule_wakeup(self, timestamp: datetime) -> None:
        """Schedule wakeup based on current wakeup checks.

        Called before suspension to schedule automatic wakeup if needed.
        This should be called by the PrepareForSleep signal handler.
        """
        wakeup_at = execute_wakeups(self._wakeups, timestamp, self._logger)
        if wakeup_at:
            wakeup_at -= timedelta(seconds=self._wakeup_delta)
            self._logger.info("Scheduling wakeup at %s", wakeup_at)
            self._wakeup_fn(wakeup_at)
        else:
            self._logger.info("No wakeup scheduled")

    def on_resume(self) -> None:
        """Handle system resume from suspension."""
        self._reset_state("Just woke up from suspension.")

    def iteration(self, timestamp: datetime) -> None:
        self._logger.info("Starting new check iteration")

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

        # Don't suspend if a systemd inhibit lock exists
        try:
            if has_inhibit_lock():
                self._logger.info(
                    "Systemd inhibit lock detected. Not suspending but keeping idle state."
                )
                return
        except LogindDBusException:
            self._logger.warning(
                "Failed to check systemd inhibit locks. Proceeding with suspension.",
                exc_info=True,
            )

        # determine potential wake ups to check if sleep time is sufficient
        wakeup_at = execute_wakeups(self._wakeups, timestamp, self._logger)
        if wakeup_at is None:
            self._logger.debug("No automatic wakeup required")
        else:
            self._logger.debug("System wakeup required at %s", wakeup_at)

            # apply configured wakeup delta
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

        # wakeup will be scheduled by PrepareForSleep signal handler
        self._reset_state("Going to suspend")
        self._sleep_fn(wakeup_at)


def _compute_max_iterations(run_for: int | None, interval: float) -> int | None:
    if run_for is None:
        return None
    return max(1, math.ceil(run_for / interval))


def loop(
    processor: Processor,
    interval: float,
    *,
    run_for: int | None = None,
) -> None:
    """Run the main loop of the daemon with DBus integration.

    Args:
        processor:
            the processor to use for handling the suspension computations
        interval:
            the length of one iteration of the main loop in seconds
        run_for:
            if specified, run the main loop for the specified amount of seconds
            before terminating (approximately)
    """
    # initialize DBus main loop
    DBusGMainLoop(set_as_default=True)
    main_loop = GLib.MainLoop()

    # set up PrepareForSleep signal handler
    def on_prepare_for_sleep(going_to_sleep: bool) -> None:
        _logger.info(
            "PrepareForSleep signal received: going_to_sleep=%s", going_to_sleep
        )
        if going_to_sleep:
            # before suspend: always schedule wakeup (whether autosuspend or external)
            processor.schedule_wakeup(datetime.now(UTC))
        else:
            # after resume: reset processor state
            processor.on_resume()

    try:
        bus = dbus.SystemBus()
        bus.add_signal_receiver(
            on_prepare_for_sleep,
            signal_name="PrepareForSleep",
            dbus_interface="org.freedesktop.login1.Manager",
            bus_name="org.freedesktop.login1",
            path="/org/freedesktop/login1",
        )
        _logger.debug("Subscribed to PrepareForSleep signal")
    except dbus.exceptions.DBusException:
        _logger.warning(
            "Failed to subscribe to PrepareForSleep signal. Wake ups will not work.",
            exc_info=True,
        )

    # set up interval timer
    # list for mutable closure variable
    iteration_count = [0]
    max_iterations = _compute_max_iterations(run_for, interval)

    def timer_callback() -> bool:
        if max_iterations is not None:
            if iteration_count[0] >= max_iterations:
                _logger.info("Max iterations reached, stopping main loop")
                main_loop.quit()
                return False
            iteration_count[0] += 1

        processor.iteration(datetime.now(UTC))
        return True

    def timer_callback_once() -> bool:
        timer_callback()
        return False

    GLib.timeout_add_seconds(int(interval), timer_callback)
    # run first iteration immediately
    GLib.idle_add(timer_callback_once)

    _logger.info("Starting main loop")
    try:
        main_loop.run()
    except KeyboardInterrupt:
        _logger.info("Interrupted, stopping")
    finally:
        main_loop.quit()


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
        "Configuring check %s with class %s from module %s using config parameters %s",
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


def discover_available_checks(
    internal_module: str, check_type: type[CheckType]
) -> list[type[CheckType]]:
    """Find all concrete subclasses of Check in the given module.

    Args:
        internal_module: either "activity" or "wakeup" to specify which module to search
        check_type: the base check type class (Activity or Wakeup) to find subclasses of

    Returns:
        List of concrete check classes found in the specified module
    """
    module_name = f"autosuspend.checks.{internal_module}"
    module = importlib.import_module(module_name)

    available_checks = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, check_type)
            # exclude the base class itself
            and obj is not check_type
            and not inspect.isabstract(obj)
        ):
            available_checks.append(obj)

    return available_checks


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


def parse_config(config_file: Path) -> configparser.ConfigParser:
    """Parse the configuration file.

    Args:
        config_file:
            Path to the file to parse
    """
    _logger.debug("Reading config file %s", config_file)
    config = configparser.ConfigParser(
        interpolation=configparser.ExtendedInterpolation()
    )
    with config_file.open("r") as f:
        config.read_file(f)
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

    default_config_path = Path("/etc/autosuspend.conf")
    default_config: Path | None = None
    if default_config_path.exists():
        default_config = default_config_path
    parser.add_argument(
        "-c",
        "--config",
        dest="config_file",
        type=Path,
        default=default_config,
        required=default_config is None,
        metavar="FILE",
        help="The config file to use",
    )

    logging_group = parser.add_mutually_exclusive_group()
    logging_group.add_argument(
        "-l",
        "--logging",
        type=Path,
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

    parser_schema = subparsers.add_parser(
        "schema",
        help="Prints a schema of the available configruation sections and options",
    )
    parser_schema.set_defaults(func=main_schema)

    result = parser.parse_args(args)

    _logger.debug("Parsed command line arguments %s", result)

    return result


def configure_logging(config_file: Path | None, debug: bool) -> None:
    """Configure the python :mod:`logging` system.

    Assumes that either a config file is provided, or debugging is enabled.
    Both together are not possible.

    Args:
        config_file:
            path to a logging configuration file
        debug:
            if ``True``, enable debug logging
    """
    if config_file:
        try:
            with config_file.open("r") as f:
                logging.config.fileConfig(f)
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


def main_version(
    _: argparse.Namespace,
    config: configparser.ConfigParser,  # noqa: ARG001
) -> None:
    print(version("autosuspend"))  # noqa: T201


def main_schema(
    _: argparse.Namespace,
    config: configparser.ConfigParser,  # noqa: ARG001
) -> None:
    activity_checks = discover_available_checks("activity", Activity)  # type: ignore
    wakeup_checks = discover_available_checks("wakeup", Wakeup)  # type: ignore
    schema = ConfigSchema(
        general_parameters=GENERAL_PARAMETERS,
        activity_checks={
            check.__name__: check.config_parameters for check in activity_checks
        },
        wakeup_checks={
            check.__name__: check.config_parameters for check in wakeup_checks
        },
    )

    print(schema.to_json())  # noqa: T201


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

    # get the sleep and wakeup functions
    sleep_fn = get_notify_and_suspend_func(config)
    wakeup_fn = get_schedule_wakeup_func(config)

    # create processor
    processor = Processor(
        checks,
        wakeups,
        config.getfloat("general", "idle_time", fallback=300),
        config.getfloat("general", "min_sleep_time", fallback=1200),
        get_wakeup_delta(config),
        sleep_fn,
        wakeup_fn,
        all_activities=args.all_checks,
    )

    loop(
        processor,
        config.getfloat("general", "interval", fallback=60),
        run_for=args.run_for,
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run the daemon."""
    args = parse_arguments(argv)

    configure_logging(args.logging, args.debug)

    config = parse_config(args.config_file)

    args.func(args, config)


if __name__ == "__main__":
    main()
