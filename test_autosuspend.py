import os.path
import re
import subprocess

import psutil

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


class TestUsers(object):

    def test_no_users(self, monkeypatch):

        def data():
            return []
        monkeypatch.setattr(psutil, 'users', data)

        assert autosuspend.Users('users', re.compile('.*'), re.compile('.*'),
                                 re.compile('.*')).check() is None

    def test_smoke(self):
        autosuspend.Users('users', re.compile('.*'), re.compile('.*'),
                          re.compile('.*')).check()

    def test_matching_users(self, monkeypatch):

        def data():
            return [psutil._common.suser('foo', 'pts1', 'host', 12345, 12345)]
        monkeypatch.setattr(psutil, 'users', data)

        assert autosuspend.Users('users', re.compile('.*'), re.compile('.*'),
                                 re.compile('.*')).check() is not None

    def test_non_matching_user(self, monkeypatch):

        def data():
            return [psutil._common.suser('foo', 'pts1', 'host', 12345, 12345)]
        monkeypatch.setattr(psutil, 'users', data)

        assert autosuspend.Users('users', re.compile('narf'), re.compile('.*'),
                                 re.compile('.*')).check() is None


class TestProcesses(object):

    class StubProcess(object):

        def __init__(self, name):
            self._name = name

        def name(self):
            return self._name

    def test_matching_process(self, monkeypatch):

        def data():
            return [self.StubProcess('blubb'), self.StubProcess('nonmatching')]
        monkeypatch.setattr(psutil, 'process_iter', data)

        assert autosuspend.Processes(
            'foo', ['dummy', 'blubb', 'other']).check() is not None

    def test_non_matching_process(self, monkeypatch):

        def data():
            return [self.StubProcess('asdfasdf'),
                    self.StubProcess('nonmatching')]
        monkeypatch.setattr(psutil, 'process_iter', data)

        assert autosuspend.Processes(
            'foo', ['dummy', 'blubb', 'other']).check() is None
