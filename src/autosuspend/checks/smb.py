import configparser
import subprocess
from typing import Self

from . import Activity, SevereCheckError, TemporaryCheckError


class Smb(Activity):
    @classmethod
    def create(
        cls: type[Self],
        name: str,
        config: configparser.SectionProxy | None,  # noqa: ARG003
    ) -> Self:
        return cls(name)

    def _safe_get_status(self) -> str:
        try:
            return subprocess.check_output(["smbstatus", "-b"]).decode("utf-8")
        except FileNotFoundError as error:
            raise SevereCheckError("smbstatus binary not found") from error
        except subprocess.CalledProcessError as error:
            raise TemporaryCheckError("Unable to execute smbstatus") from error

    def check(self) -> str | None:
        status_output = self._safe_get_status()

        self.logger.debug("Received status output:\n%s", status_output)

        connections = []
        start_seen = False
        for line in status_output.splitlines():
            if start_seen:
                connections.append(line)
            else:
                if line.startswith("----"):
                    start_seen = True

        if connections:
            return "SMB clients are connected:\n{}".format("\n".join(connections))
        else:
            return None
