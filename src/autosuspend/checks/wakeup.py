from contextlib import suppress

# isort: off

from .command import CommandWakeup as Command  # noqa
from .linux import File  # noqa
from .stub import Periodic  # noqa

with suppress(ModuleNotFoundError):
    from .ical import Calendar  # noqa
with suppress(ModuleNotFoundError):
    from .xpath import XPathWakeup as XPath  # noqa
    from .xpath import XPathDeltaWakeup as XPathDelta  # noqa
with suppress(ModuleNotFoundError):
    from .systemd import SystemdTimer  # noqa

# isort: on
