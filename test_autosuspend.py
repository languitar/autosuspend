import configparser
import logging
import os.path
import re
import socket
import subprocess
import unittest.mock

import psutil

import pytest

import requests.exceptions

import autosuspend


class TestCheck(object):

    class DummyCheck(autosuspend.Check):

        @classmethod
        def create(cls, name, config):
            pass

        def check(self):
            pass

    def test_name(self):
        name = 'test'
        assert self.DummyCheck(name).name == name

    def test_name_default(self):
        assert self.DummyCheck().name is not None

    def test_str(self):
        assert isinstance(str(self.DummyCheck('test')), str)


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

    def test_call_error(self, mocker):
        mocker.patch('subprocess.check_output',
                     side_effect=subprocess.CalledProcessError(2, 'cmd'))

        with pytest.raises(autosuspend.SevereCheckError):
            autosuspend.Smb('foo').check()

    def test_create(self):
        assert isinstance(autosuspend.Smb.create('name', None),
                          autosuspend.Smb)


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

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           name = name.*name
                           terminal = term.*term
                           host = host.*host''')

        check = autosuspend.Users.create('name', parser['section'])

        assert check._user_regex == re.compile('name.*name')
        assert check._terminal_regex == re.compile('term.*term')
        assert check._host_regex == re.compile('host.*host')

    def test_create_regex_error(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           name = name.*name
                           terminal = term.[[a-9]term
                           host = host.*host''')

        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.Users.create('name', parser['section'])


class TestProcesses(object):

    class StubProcess(object):

        def __init__(self, name):
            self._name = name

        def name(self):
            return self._name

    class RaisingProcess(object):

        def name(self):
            raise psutil.NoSuchProcess(42)

    def test_matching_process(self, monkeypatch):

        def data():
            return [self.StubProcess('blubb'), self.StubProcess('nonmatching')]
        monkeypatch.setattr(psutil, 'process_iter', data)

        assert autosuspend.Processes(
            'foo', ['dummy', 'blubb', 'other']).check() is not None

    def test_ignore_no_such_process(self, monkeypatch):

        def data():
            return [self.RaisingProcess()]
        monkeypatch.setattr(psutil, 'process_iter', data)

        autosuspend.Processes('foo', ['dummy']).check()

    def test_non_matching_process(self, monkeypatch):

        def data():
            return [self.StubProcess('asdfasdf'),
                    self.StubProcess('nonmatching')]
        monkeypatch.setattr(psutil, 'process_iter', data)

        assert autosuspend.Processes(
            'foo', ['dummy', 'blubb', 'other']).check() is None

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           processes = foo, bar, narf''')
        assert autosuspend.Processes.create(
            'name', parser['section'])._processes == ['foo', 'bar', 'narf']

    def test_create_no_entry(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.Processes.create('name', parser['section'])



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

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           ports = 10,20,30''')
        assert autosuspend.ActiveConnection.create(
            'name', parser['section'])._ports == set([10, 20, 30])

    def test_create_no_entry(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.ActiveConnection.create('name', parser['section'])

    def test_create_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           ports = 10,20xx,30''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.ActiveConnection.create('name', parser['section'])


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

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           threshold = 3.2''')
        assert autosuspend.Load.create(
            'name', parser['section'])._threshold == 3.2

    def test_create_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           threshold = narf''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.Load.create('name', parser['section'])



class TestMpd(object):

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
        mock_instance.status.assert_called_once_with()
        mock_instance.close.assert_called_once_with()
        mock_instance.disconnect.assert_called_once_with()

    def test_handle_connection_errors(self):

        check = autosuspend.Mpd('test', None, None, None)

        def _get_state():
            raise ConnectionError()

        check._get_state = _get_state

        with pytest.raises(autosuspend.TemporaryCheckError):
            check.check()

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           host = host
                           port = 1234
                           timeout = 12''')

        check = autosuspend.Mpd.create('name', parser['section'])

        assert check._host == 'host'
        assert check._port == 1234
        assert check._timeout == 12

    def test_create_port_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           host = host
                           port = string
                           timeout = 12''')

        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.Mpd.create('name', parser['section'])

    def test_create_timeout_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           host = host
                           port = 10
                           timeout = string''')

        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.Mpd.create('name', parser['section'])


class TestKodi(object):

    def test_playing(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1, "jsonrpc": "2.0",
            "result": [{"playerid": 0, "type": "audio"}]}
        mocker.patch('requests.get', return_value=mock_reply)

        assert autosuspend.Kodi('foo', 'url', 10).check() is not None

        mock_reply.json.assert_called_once_with()

    def test_not_playing(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1, "jsonrpc": "2.0", "result": []}
        mocker.patch('requests.get', return_value=mock_reply)

        assert autosuspend.Kodi('foo', 'url', 10).check() is None

        mock_reply.json.assert_called_once_with()

    def test_assertion_no_result(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0"}
        mocker.patch('requests.get', return_value=mock_reply)

        with pytest.raises(autosuspend.TemporaryCheckError):
            autosuspend.Kodi('foo', 'url', 10).check()

    def test_request_error(self, mocker):
        mocker.patch('requests.get',
                     side_effect=requests.exceptions.RequestException())

        with pytest.raises(autosuspend.TemporaryCheckError):
            autosuspend.Kodi('foo', 'url', 10).check()

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           timeout = 12''')

        check = autosuspend.Kodi.create('name', parser['section'])

        assert check._url == 'anurl'
        assert check._timeout == 12

    def test_create_timeout_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           timeout = string''')

        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.Kodi.create('name', parser['section'])


class TestPing(object):

    def test_smoke(self, mocker):
        mock = mocker.patch('subprocess.call')
        mock.return_value = 1

        hosts = ['abc', '129.123.145.42']

        assert autosuspend.Ping('name', hosts).check() is None

        assert mock.call_count == len(hosts)
        for (args, _), host in zip(mock.call_args_list, hosts):
            assert args[0][-1] == host

    def test_matching(self, mocker):
        mock = mocker.patch('subprocess.call')
        mock.return_value = 0
        assert autosuspend.Ping('name', ['foo']).check() is not None

    def test_create_missing_hosts(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.Ping.create('name', parser['section'])

    def test_create_host_splitting(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           hosts=a,b,c''')
        ping = autosuspend.Ping.create('name', parser['section'])
        assert ping._hosts == ['a', 'b', 'c']


class TestXIdleTime(object):

    def test_create_default(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        check = autosuspend.XIdleTime.create('name', parser['section'])
        assert check._timeout == 600
        assert check._ignore_process_re == re.compile(r'a^')
        assert check._ignore_users_re == re.compile(r'^a')

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              timeout = 42
                              ignore_if_process = .*test
                              ignore_users = test.*test''')
        check = autosuspend.XIdleTime.create('name', parser['section'])
        assert check._timeout == 42
        assert check._ignore_process_re == re.compile(r'.*test')
        assert check._ignore_users_re == re.compile(r'test.*test')

    def test_create_no_int(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              timeout = string''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.XIdleTime.create('name', parser['section'])

    def test_create_broken_process_re(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              ignore_if_process = [[a-9]''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.XIdleTime.create('name', parser['section'])

    def test_create_broken_users_re(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              ignore_users = [[a-9]''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.XIdleTime.create('name', parser['section'])


class TestExternalCommand(object):

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              command = narf bla  ''')
        check = autosuspend.ExternalCommand.create('name', parser['section'])
        assert check._command == 'narf bla'

    def test_create_no_command(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.ExternalCommand.create('name', parser['section'])

    def test_check(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              command = foo bar''')
        assert autosuspend.ExternalCommand.create(
            'name', parser['section']).check() is not None
        mock.assert_called_once_with('foo bar', shell=True)

    def test_check_no_match(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        mock.side_effect = subprocess.CalledProcessError(2, 'foo bar')
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              command = foo bar''')
        assert autosuspend.ExternalCommand.create(
            'name', parser['section']).check() is None
        mock.assert_called_once_with('foo bar', shell=True)


def test_execute_suspend(mocker):
    mock = mocker.patch('subprocess.check_call')
    command = ['foo', 'bar']
    autosuspend.execute_suspend(command)
    mock.assert_called_once_with(command, shell=True)


def test_execute_suspend_call_exception(mocker):
    mock = mocker.patch('subprocess.check_call')
    command = ['foo', 'bar']
    mock.side_effect = subprocess.CalledProcessError(2, command)

    spy = mocker.spy(autosuspend._logger, 'warning')

    autosuspend.execute_suspend(command)

    mock.assert_called_once_with(command, shell=True)
    assert spy.call_count == 1


def test_configure_logging_debug(mocker):
    mock = mocker.patch('logging.basicConfig')

    autosuspend.configure_logging(True)

    mock.assert_called_once_with(level=logging.DEBUG)


def test_configure_logging_standard(mocker):
    mock = mocker.patch('logging.basicConfig')

    autosuspend.configure_logging(False)

    mock.assert_called_once_with(level=logging.WARNING)


def test_configure_logging_file(mocker):
    mock = mocker.patch('logging.config.fileConfig')

    # anything that is not a boolean is treated like a file
    autosuspend.configure_logging(42)

    mock.assert_called_once_with(42)


def test_configure_logging_file_fallback(mocker):
    mock = mocker.patch('logging.config.fileConfig',
                        side_effect=RuntimeError())
    mock_basic = mocker.patch('logging.basicConfig')

    # anything that is not a boolean is treated like a file
    autosuspend.configure_logging(42)

    mock.assert_called_once_with(42)
    mock_basic.assert_called_once_with(level=logging.WARNING)


def test_set_up_checks(mocker):
    mock_class = mocker.patch('autosuspend.Mpd')
    mock_class.create.return_value = mocker.MagicMock(spec=autosuspend.Check)

    parser = configparser.ConfigParser()
    parser.read_string('''[check.Foo]
                       class = Mpd
                       enabled = True''')

    autosuspend.set_up_checks(parser)

    mock_class.create.assert_called_once_with('Foo', parser['check.Foo'])


def test_set_up_checks_not_enabled(mocker):
    mock_class = mocker.patch('autosuspend.Mpd')
    mock_class.create.return_value = mocker.MagicMock(spec=autosuspend.Check)

    parser = configparser.ConfigParser()
    parser.read_string('''[check.Foo]
                       class = Mpd
                       enabled = False''')

    with pytest.raises(autosuspend.ConfigurationError):
        autosuspend.set_up_checks(parser)


def test_set_up_checks_no_such_class(mocker):
    parser = configparser.ConfigParser()
    parser.read_string('''[check.Foo]
                       class = FooBarr
                       enabled = True''')
    with pytest.raises(autosuspend.ConfigurationError):
        autosuspend.set_up_checks(parser)


def test_set_up_checks_not_a_check(mocker):
    mock_class = mocker.patch('autosuspend.Mpd')
    mock_class.create.return_value = mocker.MagicMock()

    parser = configparser.ConfigParser()
    parser.read_string('''[check.Foo]
                       class = Mpd
                       enabled = True''')

    with pytest.raises(autosuspend.ConfigurationError):
        autosuspend.set_up_checks(parser)

    mock_class.create.assert_called_once_with('Foo', parser['check.Foo'])


class TestExecuteChecks(object):

    def test_no_checks(self, mocker):
        assert autosuspend.execute_checks(
            [], False, mocker.MagicMock()) is False

    def test_matches(self, mocker):
        matching_check = mocker.MagicMock(spec=autosuspend.Check)
        matching_check.name = 'foo'
        matching_check.check.return_value = "matches"
        assert autosuspend.execute_checks(
            [matching_check], False, mocker.MagicMock()) is True
        matching_check.check.assert_called_once_with()

    def test_only_first_called(self, mocker):
        matching_check = mocker.MagicMock(spec=autosuspend.Check)
        matching_check.name = 'foo'
        matching_check.check.return_value = "matches"
        second_check = mocker.MagicMock()
        second_check.name = 'bar'
        second_check.check.return_value = "matches"

        assert autosuspend.execute_checks(
            [matching_check, second_check],
            False,
            mocker.MagicMock()) is True
        matching_check.check.assert_called_once_with()
        second_check.check.assert_not_called()

    def test_all_called(self, mocker):
        matching_check = mocker.MagicMock(spec=autosuspend.Check)
        matching_check.name = 'foo'
        matching_check.check.return_value = "matches"
        second_check = mocker.MagicMock()
        second_check.name = 'bar'
        second_check.check.return_value = "matches"

        assert autosuspend.execute_checks(
            [matching_check, second_check],
            True,
            mocker.MagicMock()) is True
        matching_check.check.assert_called_once_with()
        second_check.check.assert_called_once_with()

    def test_ignore_temporary_errors(self, mocker):
        matching_check = mocker.MagicMock(spec=autosuspend.Check)
        matching_check.name = 'foo'
        matching_check.check.side_effect = autosuspend.TemporaryCheckError()
        second_check = mocker.MagicMock()
        second_check.name = 'bar'
        second_check.check.return_value = "matches"

        assert autosuspend.execute_checks(
            [matching_check, second_check],
            False,
            mocker.MagicMock()) is True
        matching_check.check.assert_called_once_with()
        second_check.check.assert_called_once_with()
