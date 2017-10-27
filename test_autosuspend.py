import os.path
import re
import socket
import subprocess
import unittest.mock

import psutil

import pytest

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


class TestActiveConnection(object):

    MY_PORT = 22
    MY_ADDRESS = '123.456.123.456'

    def test_smoke(self):
        autosuspend.ActiveConnection('foo', [22]).check()

    def test_connected(self, monkeypatch):

        def addresses():
            return {'dummy': [psutil._common.snic(
                socket.AF_INET, self.MY_ADDRESS, '255.255.255.0',
                None, None)]}

        def connections():
            return [psutil._common.sconn(
                -1, socket.AF_INET, socket.SOCK_STREAM,
                psutil._common.addr(self.MY_ADDRESS, self.MY_PORT),
                psutil._common.addr('42.42.42.42', 42), 'ESTABLISHED', None)]

        monkeypatch.setattr(psutil, 'net_if_addrs', addresses)
        monkeypatch.setattr(psutil, 'net_connections', connections)

        assert autosuspend.ActiveConnection(
            'foo', [10, self.MY_PORT, 30]).check() is not None

    @pytest.mark.parametrize("connection", [
        # not my port
        psutil._common.sconn(-1,
                             socket.AF_INET, socket.SOCK_STREAM,
                             psutil._common.addr(MY_ADDRESS, 32),
                             psutil._common.addr('42.42.42.42', 42),
                             'ESTABLISHED', None),
        # not my local address
        psutil._common.sconn(-1,
                             socket.AF_INET, socket.SOCK_STREAM,
                             psutil._common.addr('33.33.33.33', MY_PORT),
                             psutil._common.addr('42.42.42.42', 42),
                             'ESTABLISHED', None),
        # not my established
        psutil._common.sconn(-1,
                             socket.AF_INET, socket.SOCK_STREAM,
                             psutil._common.addr(MY_ADDRESS, MY_PORT),
                             psutil._common.addr('42.42.42.42', 42),
                             'NARF', None),
        # I am the client
        psutil._common.sconn(-1,
                             socket.AF_INET, socket.SOCK_STREAM,
                             psutil._common.addr('42.42.42.42', 42),
                             psutil._common.addr(MY_ADDRESS, MY_PORT),
                             'NARF', None),
    ])
    def test_not_connected(self, monkeypatch, connection):

        def addresses():
            return {'dummy': [psutil._common.snic(
                socket.AF_INET, self.MY_ADDRESS, '255.255.255.0',
                None, None)]}

        def connections():
            return [connection]

        monkeypatch.setattr(psutil, 'net_if_addrs', addresses)
        monkeypatch.setattr(psutil, 'net_connections', connections)

        assert autosuspend.ActiveConnection(
            'foo', [10, self.MY_PORT, 30]).check() is None


class TestLoad(object):

    def test_below(self, monkeypatch):

        threshold = 1.34

        def data():
            return [0, threshold - 0.2, 0]
        monkeypatch.setattr(os, 'getloadavg', data)

        assert autosuspend.Load('foo', threshold).check() is None

    def test_above(self, monkeypatch):

        threshold = 1.34

        def data():
            return [0, threshold + 0.2, 0]
        monkeypatch.setattr(os, 'getloadavg', data)

        assert autosuspend.Load('foo', threshold).check() is not None


class TestMPD(object):

    def test_playing(self, monkeypatch):

        check = autosuspend.Mpd('test', None, None, None)

        def get_state():
            return {'state': 'play'}
        monkeypatch.setattr(check, '_get_state', get_state)

        assert check.check() is not None

    def test_not_playing(self, monkeypatch):

        check = autosuspend.Mpd('test', None, None, None)

        def get_state():
            return {'state': 'pause'}
        monkeypatch.setattr(check, '_get_state', get_state)

        assert check.check() is None

    def test_correct_mpd_interaction(self, mocker):
        import mpd

        mock_instance = mocker.MagicMock(spec=mpd.MPDClient)
        mock_instance.status.return_value = {'state': 'play'}
        timeout_property = mocker.PropertyMock()
        type(mock_instance).timeout = timeout_property
        mock = mocker.patch('mpd.MPDClient')
        mock.return_value = mock_instance

        host = 'foo'
        port = 42
        timeout = 17

        assert autosuspend.Mpd('name', host, port, timeout).check() is not None

        timeout_property.assert_called_once_with(timeout)
        mock_instance.connect.assert_called_once_with(host, port)
        mock_instance.status.assert_called_once()
        mock_instance.close.assert_called_once()
        mock_instance.disconnect.assert_called_once()
