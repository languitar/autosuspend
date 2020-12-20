from dataclasses import dataclass
import logging
from pathlib import Path
from typing import List, Optional

from .systemd import list_logind_sessions


@dataclass
class XorgSession:
    display: int
    user: str


_logger = logging.getLogger(__name__)


def list_sessions_sockets(socket_path: Optional[Path] = None) -> List[XorgSession]:
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


def list_sessions_logind() -> List[XorgSession]:
    """List running X sessions using logind.

    This method assumes that a ``Display`` variable is set in the logind
    sessions.

    Raises:
        LogindDBusException: cannot connect or extract sessions
    """
    results = []
    for session_id, properties in list_logind_sessions():
        if "Name" in properties and "Display" in properties:
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
        else:
            _logger.debug(
                "Skipping session %s because it does not contain "
                "a user name and a display",
                session_id,
            )
    return results
