import os.path
import subprocess

import autosuspend


class TestSmb(object):

    def test_no_connections(self, monkeypatch):
        def return_data(*args, **kwargs):
            with open(os.path.join(os.path.dirname(__file__), 'test_data',
                                   'smbstatus_no_connections'), 'rb') as f:
                return f.read()
        monkeypatch.setattr(subprocess, 'check_output', return_data)

        assert autosuspend.Smb('foo').check() is None

    def test_with_connections(self, monkeypatch):
        def return_data(*args, **kwargs):
            with open(os.path.join(os.path.dirname(__file__), 'test_data',
                                   'smbstatus_with_connections'), 'rb') as f:
                return f.read()
        monkeypatch.setattr(subprocess, 'check_output', return_data)

        assert autosuspend.Smb('foo').check() is not None
        assert len(autosuspend.Smb('foo').check().splitlines()) == 3
