import pytest

from autosuspend.util.systemd import list_logind_sessions


def test_list_logind_sessions():
    pytest.importorskip('dbus')

    assert list_logind_sessions() is not None
