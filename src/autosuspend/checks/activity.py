import configparser
from contextlib import suppress
import copy
import os
from pathlib import Path
import re
import subprocess
from typing import Callable, List, Optional, Pattern
import warnings

import psutil

from . import Activity, ConfigurationError, SevereCheckError, TemporaryCheckError
from ..util.systemd import LogindDBusException
from ..util.xorg import list_sessions_logind, list_sessions_sockets, XorgSession


# isort: off

from .command import CommandActivity as ExternalCommand  # noqa
from .linux import (  # noqa
    ActiveConnection,  # noqa
    Load,  # noqa
    NetworkBandwidth,  # noqa
    Ping,  # noqa
    Processes,  # noqa
    Users,  # noqa
)
from .smb import Smb  # noqa

with suppress(ModuleNotFoundError):
    from .ical import ActiveCalendarEvent  # noqa
with suppress(ModuleNotFoundError):
    from .json import JsonPath  # noqa
with suppress(ModuleNotFoundError):
    from .logs import LastLogActivity  # noqa
with suppress(ModuleNotFoundError):
    from .xpath import XPathActivity as XPath  # noqa
with suppress(ModuleNotFoundError):
    from .systemd import LogindSessionsIdle  # noqa
with suppress(ModuleNotFoundError):
    from .mpd import Mpd  # noqa

from .kodi import Kodi, KodiIdleTime  # noqa

# isort: on


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
                    "Regular expression is invalid: {}".format(error),
                ) from error
            except ValueError as error:
                raise ConfigurationError(
                    "Unable to parse configuration: {}".format(error),
                ) from error

    @staticmethod
    def _get_session_method(method: str) -> Callable[[], List[XorgSession]]:
        if method == "sockets":
            return list_sessions_sockets
        elif method == "logind":
            return list_sessions_logind
        else:
            raise ValueError("Unknown session discovery method {}".format(method))

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
        self._provide_sessions: Callable[[], List[XorgSession]]
        self._provide_sessions = self._get_session_method(method)
        self._ignore_process_re = ignore_process_re
        self._ignore_users_re = ignore_users_re

    @staticmethod
    def _get_user_processes(user: str) -> List[psutil.Process]:
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

    def _safe_provide_sessions(self) -> List[XorgSession]:
        try:
            return self._provide_sessions()
        except LogindDBusException as error:
            raise TemporaryCheckError(error) from error

    def _get_idle_time(self, session: XorgSession) -> float:
        env = copy.deepcopy(os.environ)
        env["DISPLAY"] = ":{}".format(session.display)
        env["XAUTHORITY"] = str(Path("~" + session.user).expanduser() / ".Xauthority")

        try:
            idle_time_output = subprocess.check_output(  # noqa: S603, S607
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

    def check(self) -> Optional[str]:
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
                    "X session {} of user {} "
                    "has idle time {} < threshold {}".format(
                        session.display, session.user, idle_time, self._timeout
                    )
                )

        return None
