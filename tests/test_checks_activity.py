import pytest

from autosuspend.checks import Activity


@pytest.mark.parametrize(
    "name",
    [
        "ActiveCalendarEvent",
        "ActiveConnection",
        "ExternalCommand",
        "JsonPath",
        "Kodi",
        "KodiIdleTime",
        "LastLogActivity",
        "Load",
        "LogindSessionsIdle",
        "Mpd",
        "NetworkBandwidth",
        "Ping",
        "Processes",
        "Smb",
        "Users",
        "XIdleTime",
        "XPath",
    ],
)
def test_legacy_check_names_are_available(name: str) -> None:
    res = __import__("autosuspend.checks.activity", fromlist=[name])
    assert issubclass(getattr(res, name), Activity)
