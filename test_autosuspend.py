import configparser
from datetime import datetime, timedelta, timezone
import http.server
import logging
import os.path
import pwd
import re
import socket
import subprocess
import sys
import threading

import psutil

import pytest

import requests
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

    @staticmethod
    def create_suser(name, terminal, host, started, pid):
        try:
            return psutil._common.suser(name, terminal, host, started, pid)
        except TypeError:
            # psutil 5.0
            return psutil._common.suser(name, terminal, host, started)

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
            return [self.create_suser('foo', 'pts1', 'host', 12345, 12345)]
        monkeypatch.setattr(psutil, 'users', data)

        assert autosuspend.Users('users', re.compile('.*'), re.compile('.*'),
                                 re.compile('.*')).check() is not None

    def test_non_matching_user(self, monkeypatch):

        def data():
            return [self.create_suser('foo', 'pts1', 'host', 12345, 12345)]
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
                (self.MY_ADDRESS, self.MY_PORT),
                ('42.42.42.42', 42), 'ESTABLISHED', None)]

        monkeypatch.setattr(psutil, 'net_if_addrs', addresses)
        monkeypatch.setattr(psutil, 'net_connections', connections)

        assert autosuspend.ActiveConnection(
            'foo', [10, self.MY_PORT, 30]).check() is not None

    @pytest.mark.parametrize("connection", [
        # not my port
        psutil._common.sconn(-1,
                             socket.AF_INET, socket.SOCK_STREAM,
                             (MY_ADDRESS, 32),
                             ('42.42.42.42', 42),
                             'ESTABLISHED', None),
        # not my local address
        psutil._common.sconn(-1,
                             socket.AF_INET, socket.SOCK_STREAM,
                             ('33.33.33.33', MY_PORT),
                             ('42.42.42.42', 42),
                             'ESTABLISHED', None),
        # not my established
        psutil._common.sconn(-1,
                             socket.AF_INET, socket.SOCK_STREAM,
                             (MY_ADDRESS, MY_PORT),
                             ('42.42.42.42', 42),
                             'NARF', None),
        # I am the client
        psutil._common.sconn(-1,
                             socket.AF_INET, socket.SOCK_STREAM,
                             ('42.42.42.42', 42),
                             (MY_ADDRESS, MY_PORT),
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


class TestNetworkBandwidth(object):

    @pytest.fixture
    def stub_server(self):
        server = http.server.HTTPServer(('localhost', 0),
                                        http.server.SimpleHTTPRequestHandler)
        threading.Thread(target=server.serve_forever).start()
        yield server
        server.shutdown()

    def test_smoke(self, stub_server):
        check = autosuspend.NetworkBandwidth(
            'name', psutil.net_if_addrs().keys(), 0, 0)
        # make some traffic
        requests.get('http://localhost:{}/'.format(
            stub_server.server_address[1]))
        assert check.check() is not None

    @pytest.fixture
    def mock_interfaces(self, mocker):
        mock = mocker.patch('psutil.net_if_addrs')
        mock.return_value = {'foo': None, 'bar': None, 'baz': None}

    def test_create(self, mock_interfaces):
        parser = configparser.ConfigParser()
        parser.read_string('''
[section]
interfaces = foo, baz
threshold_send = 200
threshold_receive = 300
''')
        check = autosuspend.NetworkBandwidth.create('name', parser['section'])
        assert set(check._interfaces) == set(['foo', 'baz'])
        assert check._threshold_send == 200
        assert check._threshold_receive == 300

    def test_create_default(self, mock_interfaces):
        parser = configparser.ConfigParser()
        parser.read_string('''
[section]
interfaces = foo, baz
''')
        check = autosuspend.NetworkBandwidth.create('name', parser['section'])
        assert set(check._interfaces) == set(['foo', 'baz'])
        assert check._threshold_send == 100
        assert check._threshold_receive == 100

    @pytest.mark.parametrize("config,error_match", [
        ('''
[section]
interfaces = foo, NOTEXIST
threshold_send = 200
threshold_receive = 300
''', r'does not exist'),
        ('''
[section]
threshold_send = 200
threshold_receive = 300
''', r'configuration key: \'interfaces\''),
        ('''
[section]
interfaces =
threshold_send = 200
threshold_receive = 300
''', r'No interfaces configured'),
        ('''
[section]
interfaces = foo, bar
threshold_send = xxx
''', r'Threshold in wrong format'),
        ('''
[section]
interfaces = foo, bar
threshold_receive = xxx
''', r'Threshold in wrong format'),
    ])
    def test_create_error(self, mock_interfaces, config, error_match):
        parser = configparser.ConfigParser()
        parser.read_string(config)
        with pytest.raises(autosuspend.ConfigurationError, match=error_match):
            autosuspend.NetworkBandwidth.create('name', parser['section'])

    @pytest.mark.parametrize('send_threshold,receive_threshold,match', [
        (sys.float_info.max, 0, 'receive'),
        (0, sys.float_info.max, 'sending'),
    ])
    def test_with_activity(self, send_threshold, receive_threshold, match,
                           stub_server):
        check = autosuspend.NetworkBandwidth(
            'name', psutil.net_if_addrs().keys(),
            send_threshold, receive_threshold)
        # make some traffic
        requests.get('http://localhost:{}/'.format(
            stub_server.server_address[1]))
        res = check.check()
        assert res is not None
        assert match in res

    def test_no_activity(self, stub_server):
        check = autosuspend.NetworkBandwidth(
            'name', psutil.net_if_addrs().keys(),
            sys.float_info.max, sys.float_info.max)
        # make some traffic
        requests.get('http://localhost:{}/'.format(
            stub_server.server_address[1]))
        assert check.check() is None


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
        assert check._ignore_users_re == re.compile(r'a^')
        assert check._provide_sessions == check._list_sessions_sockets

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              timeout = 42
                              ignore_if_process = .*test
                              ignore_users = test.*test
                              method = logind''')
        check = autosuspend.XIdleTime.create('name', parser['section'])
        assert check._timeout == 42
        assert check._ignore_process_re == re.compile(r'.*test')
        assert check._ignore_users_re == re.compile(r'test.*test')
        assert check._provide_sessions == check._list_sessions_logind

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

    def test_create_unknown_method(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              method = asdfasdf''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.XIdleTime.create('name', parser['section'])

    def test_list_sessions_logind(self, mocker):
        mock = mocker.patch('autosuspend._list_logind_sessions')
        mock.return_value = [('c1', {'Name': 'foo'}),
                             ('c2', {'Display': 'asdfasf'}),
                             ('c3', {'Name': 'hello', 'Display': 'nonumber'}),
                             ('c4', {'Name': 'hello', 'Display': '3'})]

        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        check = autosuspend.XIdleTime.create('name', parser['section'])
        assert check._list_sessions_logind() == [(3, 'hello')]

    def test_list_sessions_socket(self, mocker):
        mock_glob = mocker.patch('glob.glob')
        mock_glob.return_value = ['/tmp/.X11-unix/X0',
                                  '/tmp/.X11-unix/X42',
                                  '/tmp/.X11-unix/Xnum']

        stat_return = os.stat(os.path.realpath(__file__))
        this_user = pwd.getpwuid(stat_return.st_uid)
        mock_stat = mocker.patch('os.stat')
        mock_stat.return_value = stat_return

        mock_pwd = mocker.patch('pwd.getpwuid')
        mock_pwd.return_value = this_user

        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        check = autosuspend.XIdleTime.create('name', parser['section'])
        assert check._list_sessions_sockets() == [(0, this_user.pw_name),
                                                  (42, this_user.pw_name)]


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


class TestXPath(object):

    def test_matching(self, mocker):
        mock_reply = mocker.MagicMock()
        text_property = mocker.PropertyMock()
        type(mock_reply).text = text_property
        text_property.return_value = "<a></a>"
        mock_method = mocker.patch('requests.get', return_value=mock_reply)

        url = 'nourl'
        assert autosuspend.XPath('foo', '/a', url, 5).check() is not None

        mock_method.assert_called_once_with(url, timeout=5)
        text_property.assert_called_once_with()

    def test_not_matching(self, mocker):
        mock_reply = mocker.MagicMock()
        text_property = mocker.PropertyMock()
        type(mock_reply).text = text_property
        text_property.return_value = "<a></a>"
        mocker.patch('requests.get', return_value=mock_reply)

        assert autosuspend.XPath('foo', '/b', 'nourl', 5).check() is None

    def test_broken_xml(self, mocker):
        with pytest.raises(autosuspend.TemporaryCheckError):
            mock_reply = mocker.MagicMock()
            text_property = mocker.PropertyMock()
            type(mock_reply).text = text_property
            text_property.return_value = "//broken"
            mocker.patch('requests.get', return_value=mock_reply)

            autosuspend.XPath('foo', '/b', 'nourl', 5).check()

    def test_xpath_prevalidation(self):
        with pytest.raises(autosuspend.ConfigurationError,
                           match=r'^Invalid xpath.*'):
            parser = configparser.ConfigParser()
            parser.read_string('''[section]
                               xpath=|34/ad
                               url=nourl''')
            autosuspend.XPath.create('name', parser['section'])

    @pytest.mark.parametrize('entry,', ['xpath', 'url'])
    def test_missing_config_entry(self, entry):
        with pytest.raises(autosuspend.ConfigurationError,
                           match=r"^No '" + entry + "'.*"):
            parser = configparser.ConfigParser()
            parser.read_string('''[section]
                               xpath=/valid
                               url=nourl''')
            del parser['section'][entry]
            autosuspend.XPath.create('name', parser['section'])

    def test_create_default_timeout(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           xpath=/valid
                           url=nourl''')
        check = autosuspend.XPath.create('name', parser['section'])
        assert check._timeout == 5

    def test_create_timeout(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           xpath=/valid
                           url=nourl
                           timeout=42''')
        check = autosuspend.XPath.create('name', parser['section'])
        assert check._timeout == 42

    def test_create_invalid_timeout(self):
        with pytest.raises(autosuspend.ConfigurationError,
                           match=r"^Configuration error .*"):
            parser = configparser.ConfigParser()
            parser.read_string('''[section]
                               xpath=/valid
                               url=nourl
                               timeout=xx''')
            autosuspend.XPath.create('name', parser['section'])

    def test_requests_exception(self, mocker):
        with pytest.raises(autosuspend.TemporaryCheckError):
            mock_method = mocker.patch('requests.get')
            mock_method.side_effect = requests.exceptions.ReadTimeout()

            autosuspend.XPath('foo', '/a', 'asdf', 5).check()


class TestWakeupFile(object):

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              path = /tmp/test''')
        check = autosuspend.WakeupFile.create('name', parser['section'])
        assert check._path == '/tmp/test'

    def test_create_no_path(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.WakeupFile.create('name', parser['section'])

    def test_smoke(self, tmpdir):
        file = tmpdir.join('file')
        file.write('42\n\n')
        assert autosuspend.WakeupFile('name', str(file)).check(
            datetime.now(timezone.utc)) == datetime.fromtimestamp(
                42, timezone.utc)

    def test_no_file(self, tmpdir):
        assert autosuspend.WakeupFile('name', str(tmpdir.join('narf'))).check(
            datetime.now(timezone.utc)) is None

    def test_invalid_number(self, tmpdir):
        file = tmpdir.join('filexxx')
        file.write('nonumber\n\n')
        with pytest.raises(autosuspend.TemporaryCheckError):
            autosuspend.WakeupFile('name', str(file)).check(
                datetime.now(timezone.utc))


class TestLogindSessionsIdle(object):

    def test_smoke(self):
        check = autosuspend.LogindSessionsIdle(
            'test', ['tty', 'x11', 'wayland'], ['active', 'online'])
        assert check._types == ['tty', 'x11', 'wayland']
        assert check._states == ['active', 'online']
        try:
            # only run the test if the dbus module is available (not on travis)
            import dbus  # noqa: F401
            check.check()
        except ImportError:
            pass

    def test_configure_defaults(self):
        parser = configparser.ConfigParser()
        parser.read_string('[section]')
        check = autosuspend.LogindSessionsIdle.create(
            'name', parser['section'])
        assert check._types == ['tty', 'x11', 'wayland']
        assert check._states == ['active', 'online']

    def test_configure_types(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           types=test, bla,foo''')
        check = autosuspend.LogindSessionsIdle.create(
            'name', parser['section'])
        assert check._types == ['test', 'bla', 'foo']

    def test_configure_states(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           states=test, bla,foo''')
        check = autosuspend.LogindSessionsIdle.create(
            'name', parser['section'])
        assert check._states == ['test', 'bla', 'foo']


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


def test_schedule_wakeup(mocker):
    mock = mocker.patch('subprocess.check_call')
    dt = datetime.fromtimestamp(1525270801, timezone(timedelta(hours=4)))
    autosuspend.schedule_wakeup('echo {timestamp:.0f} {iso}', dt)
    mock.assert_called_once_with('echo 1525270801 2018-05-02T18:20:01+04:00',
                                 shell=True)


def test_schedule_wakeup_call_exception(mocker):
    mock = mocker.patch('subprocess.check_call')
    mock.side_effect = subprocess.CalledProcessError(2, "foo")

    spy = mocker.spy(autosuspend._logger, 'warning')

    autosuspend.schedule_wakeup("foo", datetime.now(timezone.utc))

    mock.assert_called_once_with("foo", shell=True)
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
    mock_class.create.return_value = mocker.MagicMock(
        spec=autosuspend.Activity)

    parser = configparser.ConfigParser()
    parser.read_string('''[check.Foo]
                       class = Mpd
                       enabled = True''')

    autosuspend.set_up_checks(parser, 'check', autosuspend.Activity)

    mock_class.create.assert_called_once_with('Foo', parser['check.Foo'])


def test_set_up_checks_not_enabled(mocker):
    mock_class = mocker.patch('autosuspend.Mpd')
    mock_class.create.return_value = mocker.MagicMock(
        spec=autosuspend.Activity)

    parser = configparser.ConfigParser()
    parser.read_string('''[check.Foo]
                       class = Mpd
                       enabled = False''')

    autosuspend.set_up_checks(parser, 'check', autosuspend.Activity)

    with pytest.raises(autosuspend.ConfigurationError):
        autosuspend.set_up_checks(parser, 'check', autosuspend.Activity,
                                  error_none=True)


def test_set_up_checks_no_such_class(mocker):
    parser = configparser.ConfigParser()
    parser.read_string('''[check.Foo]
                       class = FooBarr
                       enabled = True''')
    with pytest.raises(autosuspend.ConfigurationError):
        autosuspend.set_up_checks(parser, 'check', autosuspend.Activity)


def test_set_up_checks_not_a_check(mocker):
    mock_class = mocker.patch('autosuspend.Mpd')
    mock_class.create.return_value = mocker.MagicMock()

    parser = configparser.ConfigParser()
    parser.read_string('''[check.Foo]
                       class = Mpd
                       enabled = True''')

    with pytest.raises(autosuspend.ConfigurationError):
        autosuspend.set_up_checks(parser, 'check', autosuspend.Activity)

    mock_class.create.assert_called_once_with('Foo', parser['check.Foo'])


class TestExecuteChecks(object):

    def test_no_checks(self, mocker):
        assert autosuspend.execute_checks(
            [], False, mocker.MagicMock()) is False

    def test_matches(self, mocker):
        matching_check = mocker.MagicMock(
            spec=autosuspend.Activity)
        matching_check.name = 'foo'
        matching_check.check.return_value = "matches"
        assert autosuspend.execute_checks(
            [matching_check], False, mocker.MagicMock()) is True
        matching_check.check.assert_called_once_with()

    def test_only_first_called(self, mocker):
        matching_check = mocker.MagicMock(
            spec=autosuspend.Activity)
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
        matching_check = mocker.MagicMock(
            spec=autosuspend.Activity)
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
        matching_check = mocker.MagicMock(
            spec=autosuspend.Activity)
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


class TestExecuteWakeups(object):

    def test_no_wakeups(self, mocker):
        assert autosuspend.execute_wakeups(
            [], 0, mocker.MagicMock()) is None

    def test_all_none(self, mocker):
        wakeup = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup.check.return_value = None
        assert autosuspend.execute_wakeups(
            [wakeup], 0, mocker.MagicMock()) is None

    def test_basic_return(self, mocker):
        wakeup = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        now = datetime.now(timezone.utc)
        wakeup_time = now + timedelta(seconds=10)
        wakeup.check.return_value = wakeup_time
        assert autosuspend.execute_wakeups(
            [wakeup], now, mocker.MagicMock()) == wakeup_time

    def test_soonest_taken(self, mocker):
        reference = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup.check.return_value = reference + timedelta(seconds=20)
        earlier = reference + timedelta(seconds=10)
        wakeup_earlier = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup_earlier.check.return_value = earlier
        in_between = reference + timedelta(seconds=15)
        wakeup_later = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup_later.check.return_value = in_between
        assert autosuspend.execute_wakeups(
            [wakeup, wakeup_earlier, wakeup_later],
            reference, mocker.MagicMock()) == earlier

    def test_ignore_temporary_errors(self, mocker):
        now = datetime.now(timezone.utc)

        wakeup = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup.check.return_value = now + timedelta(seconds=20)
        wakeup_error = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup_error.check.side_effect = autosuspend.TemporaryCheckError()
        wakeup_earlier = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup_earlier.check.return_value = now + timedelta(seconds=10)
        assert autosuspend.execute_wakeups(
            [wakeup, wakeup_error, wakeup_earlier],
            now, mocker.MagicMock()) == now + timedelta(seconds=10)

    def test_ignore_too_early(self, mocker):
        now = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup.check.return_value = now
        assert autosuspend.execute_wakeups(
            [wakeup], now, mocker.MagicMock()) is None
        assert autosuspend.execute_wakeups(
            [wakeup], now + timedelta(seconds=1), mocker.MagicMock()) is None


class _StubCheck(autosuspend.Activity):

    def create(cls, name, config):
        pass

    def __init__(self, name, match):
        autosuspend.Activity.__init__(self, name)
        self.match = match

    def check(self):
        return self.match


@pytest.fixture
def sleep_fn():

    class Func(object):

        def __init__(self):
            self.called = False

        def reset(self):
            self.called = False

        def __call__(self):
            self.called = True

    return Func()


@pytest.fixture
def wakeup_fn():

    class Func(object):

        def __init__(self):
            self.call_arg = None

        def reset(self):
            self.call_arg = None

        def __call__(self, arg):
            self.call_arg = arg

    return Func()


class TestProcessor(object):

    def test_smoke(self, sleep_fn, wakeup_fn):
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [],
                                          2,
                                          0,
                                          0,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)
        # should init the timestamp initially
        start = datetime.now(timezone.utc)
        processor.iteration(start, False)
        assert not sleep_fn.called
        # not yet reached
        processor.iteration(start + timedelta(seconds=1), False)
        assert not sleep_fn.called
        # time must be greater, not equal
        processor.iteration(start + timedelta(seconds=2), False)
        assert not sleep_fn.called
        # go to sleep
        processor.iteration(start + timedelta(seconds=3), False)
        assert sleep_fn.called

        sleep_fn.reset()

        # second iteration to check that the idle time got reset
        processor.iteration(start + timedelta(seconds=4), False)
        assert not sleep_fn.called
        # go to sleep again
        processor.iteration(start + timedelta(seconds=6, milliseconds=2),
                            False)
        assert sleep_fn.called

        assert wakeup_fn.call_arg is None

    def test_just_woke_up_handling(self, sleep_fn, wakeup_fn):
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [],
                                          2,
                                          0,
                                          0,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)

        # should init the timestamp initially
        start = datetime.now(timezone.utc)
        processor.iteration(start, False)
        assert not sleep_fn.called
        # should go to sleep but we just woke up
        processor.iteration(start + timedelta(seconds=3), True)
        assert not sleep_fn.called
        # start over again
        processor.iteration(start + timedelta(seconds=4), False)
        assert not sleep_fn.called
        # not yet sleeping
        processor.iteration(start + timedelta(seconds=6), False)
        assert not sleep_fn.called
        # now go to sleep
        processor.iteration(start + timedelta(seconds=7), False)
        assert sleep_fn.called

        assert wakeup_fn.call_arg is None

    def test_wakeup_blocks_sleep(self, mocker, sleep_fn, wakeup_fn):
        start = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(spec=autosuspend.Wakeup)
        wakeup.check.return_value = start + timedelta(seconds=6)
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [wakeup],
                                          2,
                                          10,
                                          0,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)

        # init iteration
        processor.iteration(start, False)
        # no activity and enough time passed to start sleeping
        processor.iteration(start + timedelta(seconds=3), False)
        assert not sleep_fn.called
        assert wakeup_fn.call_arg is None

    def test_wakeup_scheduled(self, mocker, sleep_fn, wakeup_fn):
        start = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(spec=autosuspend.Wakeup)
        wakeup.check.return_value = start + timedelta(seconds=25)
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [wakeup],
                                          2,
                                          10,
                                          0,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)

        # init iteration
        processor.iteration(start, False)
        # no activity and enough time passed to start sleeping
        processor.iteration(start + timedelta(seconds=3), False)
        assert sleep_fn.called
        assert wakeup_fn.call_arg == start + timedelta(seconds=25)

        sleep_fn.reset()
        wakeup_fn.reset()

        # ensure that wake up is not scheduled again
        processor.iteration(start + timedelta(seconds=25), False)
        assert wakeup_fn.call_arg is None

    def test_wakeup_delta_blocks(self, mocker, sleep_fn, wakeup_fn):
        start = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(spec=autosuspend.Wakeup)
        wakeup.check.return_value = start + timedelta(seconds=25)
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [wakeup],
                                          2,
                                          10,
                                          22,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)

        # init iteration
        processor.iteration(start, False)
        # no activity and enough time passed to start sleeping
        processor.iteration(start + timedelta(seconds=3), False)
        assert not sleep_fn.called

    def test_wakeup_delta_applied(self, mocker, sleep_fn, wakeup_fn):
        start = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(spec=autosuspend.Wakeup)
        wakeup.check.return_value = start + timedelta(seconds=25)
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [wakeup],
                                          2,
                                          10,
                                          4,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)

        # init iteration
        processor.iteration(start, False)
        # no activity and enough time passed to start sleeping
        processor.iteration(start + timedelta(seconds=3), False)
        assert sleep_fn.called
        assert wakeup_fn.call_arg == start + timedelta(seconds=21)
