from contextlib import suppress

# isort: off

from .command import CommandActivity as ExternalCommand  # noqa
from .linux import (  # noqa
    ActiveConnection,
    Load,
    NetworkBandwidth,
    Ping,
    Processes,
    Users,
)
from .smb import Smb  # noqa
from .systemd import LogindSessionsIdle, SystemdTimer  # noqa
from .xorg import XIdleTime  # noqa

with suppress(ModuleNotFoundError):
    from .ical import ActiveCalendarEvent  # noqa
with suppress(ModuleNotFoundError):
    from .json import JsonPath  # noqa
with suppress(ModuleNotFoundError):
    from .logs import LastLogActivity  # noqa
with suppress(ModuleNotFoundError):
    from .xpath import XPathActivity as XPath  # noqa
with suppress(ModuleNotFoundError):
    from .mpd import Mpd  # noqa

from .kodi import Kodi, KodiIdleTime  # noqa

# isort: on
