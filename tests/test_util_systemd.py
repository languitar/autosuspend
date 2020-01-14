from autosuspend.util.systemd import list_logind_sessions


def test_list_logind_sessions_empty(logind) -> None:
    assert len(list(list_logind_sessions())) == 0

    logind.AddSession('c1', 'seat0', 1042, 'auser', True)
    sessions = list(list_logind_sessions())
    assert len(sessions) == 1
    assert sessions[0][0] == 'c1'
