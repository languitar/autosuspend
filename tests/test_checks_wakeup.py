import pytest

from autosuspend.checks import Wakeup


@pytest.mark.parametrize(
    "name",
    [
        "Calendar",
        "Command",
        "File",
        "Periodic",
        "SystemdTimer",
        "XPath",
        "XPathDelta",
    ],
)
def test_legacy_check_names_are_available(name: str) -> None:
    res = __import__("autosuspend.checks.wakeup", fromlist=[name])
    assert issubclass(getattr(res, name), Wakeup)
