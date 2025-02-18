import configparser
from datetime import datetime, timezone
import subprocess

from . import (
    Activity,
    Check,
    CheckType,
    ConfigurationError,
    SevereCheckError,
    TemporaryCheckError,
    Wakeup,
)


def raise_severe_if_command_not_found(error: subprocess.CalledProcessError) -> None:
    if error.returncode == 127:
        # see http://tldp.org/LDP/abs/html/exitcodes.html
        raise SevereCheckError(f"Command '{' '.join(error.cmd)}' does not exist")


class CommandMixin(Check):
    """Mixin for configuring checks based on external commands."""

    @classmethod
    def create(
        cls: type[CheckType], name: str, config: configparser.SectionProxy
    ) -> CheckType:
        try:
            return cls(name, config["command"].strip())  # type: ignore
        except KeyError as error:
            raise ConfigurationError("Missing command specification") from error

    def __init__(self, command: str) -> None:
        self._command = command


class CommandActivity(CommandMixin, Activity):
    def __init__(self, name: str, command: str) -> None:
        CommandMixin.__init__(self, command)
        Activity.__init__(self, name)

    def check(self) -> str | None:
        try:
            subprocess.check_call(self._command, shell=True)
            return f"Command {self._command} succeeded"
        except subprocess.CalledProcessError as error:
            raise_severe_if_command_not_found(error)
            return None


class CommandWakeup(CommandMixin, Wakeup):
    """Determine wake up times based on an external command.

    The called command must return a timestamp in UTC or nothing in case no
    wake up is planned.
    """

    def __init__(self, name: str, command: str) -> None:
        CommandMixin.__init__(self, command)
        Wakeup.__init__(self, name)

    def check(self, timestamp: datetime) -> datetime | None:  # noqa: ARG002
        try:
            output = subprocess.check_output(
                self._command,
                shell=True,
            ).splitlines()[0]
            self.logger.debug(
                "Command %s succeeded with output %s", self._command, output
            )
            if output.strip():
                return datetime.fromtimestamp(float(output.strip()), timezone.utc)
            else:
                return None

        except subprocess.CalledProcessError as error:
            raise_severe_if_command_not_found(error)
            raise TemporaryCheckError(
                "Unable to call the configured command"
            ) from error
        except ValueError as error:
            raise TemporaryCheckError(
                "Return value cannot be interpreted as a timestamp"
            ) from error
