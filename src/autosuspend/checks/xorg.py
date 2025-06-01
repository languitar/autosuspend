from collections.abc import Callable
import configparser
from contextlib import suppress
import copy
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
from re import Pattern
import subprocess
import warnings

import psutil

from . import Activity, ConfigurationError, SevereCheckError, TemporaryCheckError
from ..util.systemd import list_logind_sessions, LogindDBusException


@dataclass
class XorgSession:
    display: int
    user: str


_logger = logging.getLogger(__name__)


def list_sessions_sockets(socket_path: Path | None = None) -> list[XorgSession]:
    """List running X sessions by iterating the X sockets.

    This method assumes that X servers are run under the users using the
    server.
    """
    folder = socket_path or Path("/tmp/.X11-unix/")  # noqa: S108 expected default path
    sockets = folder.glob("X*")
    _logger.debug("Found sockets: %s", sockets)

    results = []
    for sock in sockets:
        # determine the number of the X display by stripping the X prefix
        try:
            display = int(sock.name[1:])
        except ValueError:
            _logger.warning(
                "Cannot parse display number from socket %s. Skipping.",
                sock,
                exc_info=True,
            )
            continue

        # determine the user of the display
        try:
            user = sock.owner()
        except (FileNotFoundError, KeyError):
            _logger.warning(
                "Cannot get the owning user from socket %s. Skipping.",
                sock,
                exc_info=True,
            )
            continue

        results.append(XorgSession(display, user))

    return results


def list_sessions_logind() -> list[XorgSession]:
    """List running X sessions using logind.

    This method assumes that a ``Display`` variable is set in the logind
    sessions.

    Raises:
        LogindDBusException: cannot connect or extract sessions
    """
    results = []

    for session_id, properties in list_logind_sessions():
        if "Name" not in properties or "Display" not in properties:
            _logger.debug(
                "Skipping session %s because it does not contain "
                "a user name and a display",
                session_id,
            )
            continue

        try:
            results.append(
                XorgSession(
                    int(properties["Display"].replace(":", "")),
                    str(properties["Name"]),
                )
            )
        except ValueError:
            _logger.warning(
                "Unable to parse display from session properties %s",
                properties,
                exc_info=True,
            )

    return results


class XIdleTime(Activity):
    """Check that local X display have been idle long enough."""

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "XIdleTime":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            try:
                return cls(
                    name,
                    config.getint("timeout", fallback=600),
                    config.get("method", fallback="sockets"),
                    re.compile(config.get("ignore_if_process", fallback=r"a^")),
                    re.compile(config.get("ignore_users", fallback=r"a^")),
                )
            except re.error as error:
                raise ConfigurationError(
                    f"Regular expression is invalid: {error}",
                ) from error
            except ValueError as error:
                raise ConfigurationError(
                    f"Unable to parse configuration: {error}",
                ) from error

    @staticmethod
    def _get_session_method(method: str) -> Callable[[], list[XorgSession]]:
        if method == "sockets":
            return list_sessions_sockets
        elif method == "logind":
            return list_sessions_logind
        else:
            raise ValueError(f"Unknown session discovery method {method}")

    def __init__(
        self,
        name: str,
        timeout: float,
        method: str,
        ignore_process_re: Pattern,
        ignore_users_re: Pattern,
    ) -> None:
        Activity.__init__(self, name)
        self._timeout = timeout
        self._provide_sessions: Callable[[], list[XorgSession]]
        self._provide_sessions = self._get_session_method(method)
        self._ignore_process_re = ignore_process_re
        self._ignore_users_re = ignore_users_re

    @staticmethod
    def _get_user_processes(user: str) -> list[psutil.Process]:
        user_processes = []
        for process in psutil.process_iter():
            with suppress(
                psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied
            ):
                if process.username() == user:
                    user_processes.append(process.name())
        return user_processes

    def _is_skip_process_running(self, user: str) -> bool:
        for process in self._get_user_processes(user):
            if self._ignore_process_re.match(process) is not None:
                self.logger.debug(
                    "Process %s with pid %s matches the ignore regex '%s'."
                    " Skipping idle time check for this user.",
                    process.name(),
                    process.pid,
                    self._ignore_process_re,
                )
                return True

        return False

    def _safe_provide_sessions(self) -> list[XorgSession]:
        try:
            return self._provide_sessions()
        except LogindDBusException as error:
            raise TemporaryCheckError(error) from error

    def _get_idle_time(self, session: XorgSession) -> float:
        env = copy.deepcopy(os.environ)
        env["DISPLAY"] = f":{session.display}"
        env["XAUTHORITY"] = str(Path("~" + session.user).expanduser() / ".Xauthority")

        try:
            idle_time_output = subprocess.check_output(
                ["sudo", "-u", session.user, "xprintidle"], env=env
            )
            return float(idle_time_output.strip()) / 1000.0
        except FileNotFoundError as error:
            raise SevereCheckError("sudo executable not found") from error
        except (subprocess.CalledProcessError, ValueError) as error:
            self.logger.warning(
                "Unable to determine the idle time for display %s.",
                session.display,
                exc_info=True,
            )
            raise TemporaryCheckError("Unable to call xprintidle") from error

    def check(self) -> str | None:
        for session in self._safe_provide_sessions():
            self.logger.info("Checking session %s", session)

            # check whether this users should be ignored completely
            if self._ignore_users_re.match(session.user) is not None:
                self.logger.debug("Skipping user '%s' due to request", session.user)
                continue

            # check whether any of the running processes of this user matches
            # the ignore regular expression. In that case we skip idletime
            # checking because we assume the user has a process running that
            # inevitably tampers with the idle time.
            if self._is_skip_process_running(session.user):
                continue

            idle_time = self._get_idle_time(session)
            self.logger.debug(
                "Idle time for display %s of user %s is %s seconds.",
                session.display,
                session.user,
                idle_time,
            )

            if idle_time < self._timeout:
                return (
                    f"X session {session.display} of user {session.user} "
                    f"has idle time {idle_time} < threshold {self._timeout}"
                )

        return None
