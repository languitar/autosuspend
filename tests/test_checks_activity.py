from collections import namedtuple
import configparser
import os
import os.path
import pwd
import re
import socket
import subprocess
import sys

import psutil
import pytest
import requests

from autosuspend.checks import (ConfigurationError,
                                SevereCheckError,
                                TemporaryCheckError)
from autosuspend.checks.activity import (ActiveCalendarEvent,
                                         ActiveConnection,
                                         ExternalCommand,
                                         Kodi,
                                         KodiIdleTime,
                                         Load,
                                         LogindSessionsIdle,
                                         Mpd,
                                         NetworkBandwidth,
                                         Ping,
                                         Processes,
                                         Smb,
                                         Users,
                                         XIdleTime,
                                         XPath)


snic = namedtuple('snic', ['family', 'address', 'netmask', 'broadcast', 'ptp'])


class TestSmb(object):

    def test_no_connections(self, monkeypatch):
        def return_data(*args, **kwargs):
            with open(os.path.join(os.path.dirname(__file__), 'test_data',
                                   'smbstatus_no_connections'), 'rb') as f:
                return f.read()
        monkeypatch.setattr(subprocess, 'check_output', return_data)

        assert Smb('foo').check() is None

    def test_with_connections(self, monkeypatch):
        def return_data(*args, **kwargs):
            with open(os.path.join(os.path.dirname(__file__), 'test_data',
                                   'smbstatus_with_connections'), 'rb') as f:
                return f.read()
        monkeypatch.setattr(subprocess, 'check_output', return_data)

        assert Smb('foo').check() is not None
        assert len(Smb('foo').check().splitlines()) == 3

    def test_call_error(self, mocker):
        mocker.patch('subprocess.check_output',
                     side_effect=subprocess.CalledProcessError(2, 'cmd'))

        with pytest.raises(SevereCheckError):
            Smb('foo').check()

    def test_create(self):
        assert isinstance(Smb.create('name', None), Smb)


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

        assert Users('users', re.compile('.*'), re.compile('.*'),
                     re.compile('.*')).check() is None

    def test_smoke(self):
        Users('users', re.compile('.*'), re.compile('.*'),
              re.compile('.*')).check()

    def test_matching_users(self, monkeypatch):

        def data():
            return [self.create_suser('foo', 'pts1', 'host', 12345, 12345)]
        monkeypatch.setattr(psutil, 'users', data)

        assert Users('users', re.compile('.*'), re.compile('.*'),
                     re.compile('.*')).check() is not None

    def test_non_matching_user(self, monkeypatch):

        def data():
            return [self.create_suser('foo', 'pts1', 'host', 12345, 12345)]
        monkeypatch.setattr(psutil, 'users', data)

        assert Users('users', re.compile('narf'), re.compile('.*'),
                     re.compile('.*')).check() is None

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           name = name.*name
                           terminal = term.*term
                           host = host.*host''')

        check = Users.create('name', parser['section'])

        assert check._user_regex == re.compile('name.*name')
        assert check._terminal_regex == re.compile('term.*term')
        assert check._host_regex == re.compile('host.*host')

    def test_create_regex_error(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           name = name.*name
                           terminal = term.[[a-9]term
                           host = host.*host''')

        with pytest.raises(ConfigurationError):
            Users.create('name', parser['section'])


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

        assert Processes(
            'foo', ['dummy', 'blubb', 'other']).check() is not None

    def test_ignore_no_such_process(self, monkeypatch):

        def data():
            return [self.RaisingProcess()]
        monkeypatch.setattr(psutil, 'process_iter', data)

        Processes('foo', ['dummy']).check()

    def test_non_matching_process(self, monkeypatch):

        def data():
            return [self.StubProcess('asdfasdf'),
                    self.StubProcess('nonmatching')]
        monkeypatch.setattr(psutil, 'process_iter', data)

        assert Processes(
            'foo', ['dummy', 'blubb', 'other']).check() is None

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           processes = foo, bar, narf''')
        assert Processes.create(
            'name', parser['section'])._processes == ['foo', 'bar', 'narf']

    def test_create_no_entry(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(ConfigurationError):
            Processes.create('name', parser['section'])


class TestActiveCalendarEvent(object):

    def test_smoke(self, stub_server):
        address = stub_server.resource_address('long-event.ics')
        result = ActiveCalendarEvent('test', url=address, timeout=3).check()
        assert result is not None
        assert 'long-event' in result

    def test_no_event(self, stub_server):
        address = stub_server.resource_address('old-event.ics')
        assert ActiveCalendarEvent(
            'test', url=address, timeout=3).check() is None

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = foobar
                           username = user
                           password = pass
                           timeout = 3''')
        check = ActiveCalendarEvent.create('name', parser['section'])
        assert check._url == 'foobar'
        assert check._username == 'user'
        assert check._password == 'pass'
        assert check._timeout == 3


class TestActiveConnection(object):

    MY_PORT = 22
    MY_ADDRESS = '123.456.123.456'

    def test_smoke(self):
        ActiveConnection('foo', [22]).check()

    def test_connected(self, monkeypatch):

        def addresses():
            return {'dummy': [snic(
                socket.AF_INET, self.MY_ADDRESS, '255.255.255.0',
                None, None)]}

        def connections():
            return [psutil._common.sconn(
                -1, socket.AF_INET, socket.SOCK_STREAM,
                (self.MY_ADDRESS, self.MY_PORT),
                ('42.42.42.42', 42), 'ESTABLISHED', None)]

        monkeypatch.setattr(psutil, 'net_if_addrs', addresses)
        monkeypatch.setattr(psutil, 'net_connections', connections)

        assert ActiveConnection(
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
            return {'dummy': [snic(
                socket.AF_INET, self.MY_ADDRESS, '255.255.255.0',
                None, None)]}

        def connections():
            return [connection]

        monkeypatch.setattr(psutil, 'net_if_addrs', addresses)
        monkeypatch.setattr(psutil, 'net_connections', connections)

        assert ActiveConnection(
            'foo', [10, self.MY_PORT, 30]).check() is None

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           ports = 10,20,30''')
        assert ActiveConnection.create(
            'name', parser['section'])._ports == {10, 20, 30}

    def test_create_no_entry(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(ConfigurationError):
            ActiveConnection.create('name', parser['section'])

    def test_create_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           ports = 10,20xx,30''')
        with pytest.raises(ConfigurationError):
            ActiveConnection.create('name', parser['section'])


class TestLoad(object):

    def test_below(self, monkeypatch):

        threshold = 1.34

        def data():
            return [0, threshold - 0.2, 0]
        monkeypatch.setattr(os, 'getloadavg', data)

        assert Load('foo', threshold).check() is None

    def test_above(self, monkeypatch):

        threshold = 1.34

        def data():
            return [0, threshold + 0.2, 0]
        monkeypatch.setattr(os, 'getloadavg', data)

        assert Load('foo', threshold).check() is not None

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           threshold = 3.2''')
        assert Load.create(
            'name', parser['section'])._threshold == 3.2

    def test_create_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           threshold = narf''')
        with pytest.raises(ConfigurationError):
            Load.create('name', parser['section'])


class TestMpd(object):

    def test_playing(self, monkeypatch):

        check = Mpd('test', None, None, None)

        def get_state():
            return {'state': 'play'}
        monkeypatch.setattr(check, '_get_state', get_state)

        assert check.check() is not None

    def test_not_playing(self, monkeypatch):

        check = Mpd('test', None, None, None)

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

        assert Mpd('name', host, port, timeout).check() is not None

        timeout_property.assert_called_once_with(timeout)
        mock_instance.connect.assert_called_once_with(host, port)
        mock_instance.status.assert_called_once_with()
        mock_instance.close.assert_called_once_with()
        mock_instance.disconnect.assert_called_once_with()

    def test_handle_connection_errors(self):

        check = Mpd('test', None, None, None)

        def _get_state():
            raise ConnectionError()

        check._get_state = _get_state

        with pytest.raises(TemporaryCheckError):
            check.check()

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           host = host
                           port = 1234
                           timeout = 12''')

        check = Mpd.create('name', parser['section'])

        assert check._host == 'host'
        assert check._port == 1234
        assert check._timeout == 12

    def test_create_port_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           host = host
                           port = string
                           timeout = 12''')

        with pytest.raises(ConfigurationError):
            Mpd.create('name', parser['section'])

    def test_create_timeout_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           host = host
                           port = 10
                           timeout = string''')

        with pytest.raises(ConfigurationError):
            Mpd.create('name', parser['section'])


class TestNetworkBandwidth(object):

    def test_smoke(self, stub_server):
        check = NetworkBandwidth(
            'name', psutil.net_if_addrs().keys(), 0, 0)
        # make some traffic
        requests.get(stub_server.resource_address(''))
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
        check = NetworkBandwidth.create('name', parser['section'])
        assert set(check._interfaces) == {'foo', 'baz'}
        assert check._threshold_send == 200
        assert check._threshold_receive == 300

    def test_create_default(self, mock_interfaces):
        parser = configparser.ConfigParser()
        parser.read_string('''
[section]
interfaces = foo, baz
''')
        check = NetworkBandwidth.create('name', parser['section'])
        assert set(check._interfaces) == {'foo', 'baz'}
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
        with pytest.raises(ConfigurationError, match=error_match):
            NetworkBandwidth.create('name', parser['section'])

    @pytest.mark.parametrize('send_threshold,receive_threshold,match', [
        (sys.float_info.max, 0, 'receive'),
        (0, sys.float_info.max, 'sending'),
    ])
    def test_with_activity(self, send_threshold, receive_threshold, match,
                           stub_server):
        check = NetworkBandwidth(
            'name', psutil.net_if_addrs().keys(),
            send_threshold, receive_threshold)
        # make some traffic
        requests.get(stub_server.resource_address(''))
        res = check.check()
        assert res is not None
        assert match in res

    def test_no_activity(self, stub_server):
        check = NetworkBandwidth(
            'name', psutil.net_if_addrs().keys(),
            sys.float_info.max, sys.float_info.max)
        # make some traffic
        requests.get(stub_server.resource_address(''))
        assert check.check() is None


class TestKodi(object):

    def test_playing(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1, "jsonrpc": "2.0",
            "result": [{"playerid": 0, "type": "audio"}]}
        mocker.patch('requests.get', return_value=mock_reply)

        assert Kodi('foo', 'url', 10).check() is not None

        mock_reply.json.assert_called_once_with()

    def test_not_playing(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1, "jsonrpc": "2.0", "result": []}
        mocker.patch('requests.get', return_value=mock_reply)

        assert Kodi('foo', 'url', 10).check() is None

        mock_reply.json.assert_called_once_with()

    def test_assertion_no_result(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0"}
        mocker.patch('requests.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            Kodi('foo', 'url', 10).check()

    def test_request_error(self, mocker):
        mocker.patch('requests.get',
                     side_effect=requests.exceptions.RequestException())

        with pytest.raises(TemporaryCheckError):
            Kodi('foo', 'url', 10).check()

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           timeout = 12''')

        check = Kodi.create('name', parser['section'])

        assert check._url == 'anurl'
        assert check._timeout == 12

    def test_create_timeout_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           timeout = string''')

        with pytest.raises(ConfigurationError):
            Kodi.create('name', parser['section'])


class TestKodiIdleTime(object):

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           timeout = 12
                           idle_time = 42''')

        check = KodiIdleTime.create('name', parser['section'])

        assert check._url == 'anurl'
        assert check._timeout == 12
        assert check._idle_time == 42

    def test_create_timeout_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           timeout = string''')

        with pytest.raises(ConfigurationError):
            KodiIdleTime.create('name', parser['section'])

    def test_create_idle_time_no_number(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           idle_time = string''')

        with pytest.raises(ConfigurationError):
            KodiIdleTime.create('name', parser['section'])

    def test_no_result(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0"}
        mocker.patch('requests.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime('foo', 'url', 10, 42).check()

    def test_result_is_list(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0",
                                        "result": []}
        mocker.patch('requests.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime('foo', 'url', 10, 42).check()

    def test_result_no_entry(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0",
                                        "result": {}}
        mocker.patch('requests.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime('foo', 'url', 10, 42).check()

    def test_result_wrong_entry(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0",
                                        "result": {"narf": True}}
        mocker.patch('requests.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime('foo', 'url', 10, 42).check()

    def test_active(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0",
                                        "result": {
                                            "System.IdleTime(42)": True}}
        mocker.patch('requests.get', return_value=mock_reply)

        assert KodiIdleTime('foo', 'url', 10, 42).check() is not None

    def test_inactive(self, mocker):
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0",
                                        "result": {
                                            "System.IdleTime(42)": False}}
        mocker.patch('requests.get', return_value=mock_reply)

        assert KodiIdleTime('foo', 'url', 10, 42).check() is None

    def test_request_error(self, mocker):
        mocker.patch('requests.get',
                     side_effect=requests.exceptions.RequestException())

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime('foo', 'url', 10, 42).check()


class TestPing(object):

    def test_smoke(self, mocker):
        mock = mocker.patch('subprocess.call')
        mock.return_value = 1

        hosts = ['abc', '129.123.145.42']

        assert Ping('name', hosts).check() is None

        assert mock.call_count == len(hosts)
        for (args, _), host in zip(mock.call_args_list, hosts):
            assert args[0][-1] == host

    def test_matching(self, mocker):
        mock = mocker.patch('subprocess.call')
        mock.return_value = 0
        assert Ping('name', ['foo']).check() is not None

    def test_create_missing_hosts(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(ConfigurationError):
            Ping.create('name', parser['section'])

    def test_create_host_splitting(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           hosts=a,b,c''')
        ping = Ping.create('name', parser['section'])
        assert ping._hosts == ['a', 'b', 'c']


class TestXIdleTime(object):

    def test_create_default(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        check = XIdleTime.create('name', parser['section'])
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
        check = XIdleTime.create('name', parser['section'])
        assert check._timeout == 42
        assert check._ignore_process_re == re.compile(r'.*test')
        assert check._ignore_users_re == re.compile(r'test.*test')
        assert check._provide_sessions == check._list_sessions_logind

    def test_create_no_int(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              timeout = string''')
        with pytest.raises(ConfigurationError):
            XIdleTime.create('name', parser['section'])

    def test_create_broken_process_re(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              ignore_if_process = [[a-9]''')
        with pytest.raises(ConfigurationError):
            XIdleTime.create('name', parser['section'])

    def test_create_broken_users_re(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              ignore_users = [[a-9]''')
        with pytest.raises(ConfigurationError):
            XIdleTime.create('name', parser['section'])

    def test_create_unknown_method(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              method = asdfasdf''')
        with pytest.raises(ConfigurationError):
            XIdleTime.create('name', parser['section'])

    def test_list_sessions_logind(self, mocker):
        mock = mocker.patch('autosuspend.checks.activity.list_logind_sessions')
        mock.return_value = [('c1', {'Name': 'foo'}),
                             ('c2', {'Display': 'asdfasf'}),
                             ('c3', {'Name': 'hello', 'Display': 'nonumber'}),
                             ('c4', {'Name': 'hello', 'Display': '3'})]

        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        check = XIdleTime.create('name', parser['section'])
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
        check = XIdleTime.create('name', parser['section'])
        assert check._list_sessions_sockets() == [(0, this_user.pw_name),
                                                  (42, this_user.pw_name)]


class TestExternalCommand(object):

    def test_check(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              command = foo bar''')
        assert ExternalCommand.create(
            'name', parser['section']).check() is not None
        mock.assert_called_once_with('foo bar', shell=True)

    def test_check_no_match(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        mock.side_effect = subprocess.CalledProcessError(2, 'foo bar')
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              command = foo bar''')
        assert ExternalCommand.create(
            'name', parser['section']).check() is None
        mock.assert_called_once_with('foo bar', shell=True)


class TestXPath(object):

    def test_matching(self, mocker):
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mock_method = mocker.patch('requests.Session.get',
                                   return_value=mock_reply)

        url = 'nourl'
        assert XPath('foo', xpath='/a', url=url, timeout=5).check() is not None

        mock_method.assert_called_once_with(url, timeout=5)
        content_property.assert_called_once_with()

    def test_not_matching(self, mocker):
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mocker.patch('requests.Session.get', return_value=mock_reply)

        assert XPath('foo', xpath='/b', url='nourl', timeout=5).check() is None

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = url
                           xpath = /xpath
                           username = user
                           password = pass
                           timeout = 42''')
        check = XPath.create('name', parser['section'])
        assert check._xpath == '/xpath'
        assert check._url == 'url'
        assert check._username == 'user'
        assert check._password == 'pass'
        assert check._timeout == 42


class TestLogindSessionsIdle(object):

    def test_smoke(self):
        check = LogindSessionsIdle(
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
        check = LogindSessionsIdle.create('name', parser['section'])
        assert check._types == ['tty', 'x11', 'wayland']
        assert check._states == ['active', 'online']

    def test_configure_types(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           types=test, bla,foo''')
        check = LogindSessionsIdle.create('name', parser['section'])
        assert check._types == ['test', 'bla', 'foo']

    def test_configure_states(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           states=test, bla,foo''')
        check = LogindSessionsIdle.create('name', parser['section'])
        assert check._states == ['test', 'bla', 'foo']
