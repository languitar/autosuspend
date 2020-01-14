from collections import namedtuple
import configparser
import json
import os
import os.path
import pwd
import re
import socket
import subprocess
import sys

from freezegun import freeze_time
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
from . import CheckTest


snic = namedtuple('snic', ['family', 'address', 'netmask', 'broadcast', 'ptp'])


class TestSmb(CheckTest):

    def create_instance(self, name):
        return Smb(name)

    def test_no_connections(self, datadir, monkeypatch) -> None:
        def return_data(*args, **kwargs):
            return (datadir / 'smbstatus_no_connections').read_bytes()
        monkeypatch.setattr(subprocess, 'check_output', return_data)

        assert Smb('foo').check() is None

    def test_with_connections(self, datadir, monkeypatch) -> None:
        def return_data(*args, **kwargs):
            return (datadir / 'smbstatus_with_connections').read_bytes()
        monkeypatch.setattr(subprocess, 'check_output', return_data)

        res = Smb('foo').check()
        assert res is not None
        assert len(res.splitlines()) == 3

    def test_call_error(self, mocker) -> None:
        mocker.patch('subprocess.check_output',
                     side_effect=subprocess.CalledProcessError(2, 'cmd'))

        with pytest.raises(SevereCheckError):
            Smb('foo').check()

    def test_create(self) -> None:
        assert isinstance(Smb.create('name', None), Smb)


class TestUsers(CheckTest):

    def create_instance(self, name):
        return Users(name, re.compile('.*'), re.compile('.*'),
                     re.compile('.*'))

    @staticmethod
    def create_suser(name, terminal, host, started, pid):
        return psutil._common.suser(name, terminal, host, started, pid)

    def test_no_users(self, monkeypatch) -> None:

        def data():
            return []
        monkeypatch.setattr(psutil, 'users', data)

        assert Users('users', re.compile('.*'), re.compile('.*'),
                     re.compile('.*')).check() is None

    def test_smoke(self) -> None:
        Users('users', re.compile('.*'), re.compile('.*'),
              re.compile('.*')).check()

    def test_matching_users(self, monkeypatch) -> None:

        def data():
            return [self.create_suser('foo', 'pts1', 'host', 12345, 12345)]
        monkeypatch.setattr(psutil, 'users', data)

        assert Users('users', re.compile('.*'), re.compile('.*'),
                     re.compile('.*')).check() is not None

    def test_non_matching_user(self, monkeypatch) -> None:

        def data():
            return [self.create_suser('foo', 'pts1', 'host', 12345, 12345)]
        monkeypatch.setattr(psutil, 'users', data)

        assert Users('users', re.compile('narf'), re.compile('.*'),
                     re.compile('.*')).check() is None

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           name = name.*name
                           terminal = term.*term
                           host = host.*host''')

        check = Users.create('name', parser['section'])

        assert check._user_regex == re.compile('name.*name')
        assert check._terminal_regex == re.compile('term.*term')
        assert check._host_regex == re.compile('host.*host')

    def test_create_regex_error(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           name = name.*name
                           terminal = term.[[a-9]term
                           host = host.*host''')

        with pytest.raises(ConfigurationError):
            Users.create('name', parser['section'])


class TestProcesses(CheckTest):

    def create_instance(self, name):
        return Processes(name, ['foo'])

    class StubProcess:

        def __init__(self, name):
            self._name = name

        def name(self):
            return self._name

    class RaisingProcess:

        def name(self):
            raise psutil.NoSuchProcess(42)

    def test_matching_process(self, monkeypatch) -> None:

        def data():
            return [self.StubProcess('blubb'), self.StubProcess('nonmatching')]
        monkeypatch.setattr(psutil, 'process_iter', data)

        assert Processes(
            'foo', ['dummy', 'blubb', 'other']).check() is not None

    def test_ignore_no_such_process(self, monkeypatch) -> None:

        def data():
            return [self.RaisingProcess()]
        monkeypatch.setattr(psutil, 'process_iter', data)

        Processes('foo', ['dummy']).check()

    def test_non_matching_process(self, monkeypatch) -> None:

        def data():
            return [self.StubProcess('asdfasdf'),
                    self.StubProcess('nonmatching')]
        monkeypatch.setattr(psutil, 'process_iter', data)

        assert Processes(
            'foo', ['dummy', 'blubb', 'other']).check() is None

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           processes = foo, bar, narf''')
        assert Processes.create(
            'name', parser['section'])._processes == ['foo', 'bar', 'narf']

    def test_create_no_entry(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(ConfigurationError):
            Processes.create('name', parser['section'])


class TestActiveCalendarEvent(CheckTest):

    def create_instance(self, name):
        return ActiveCalendarEvent(name, url='asdfasdf', timeout=5)

    def test_smoke(self, datadir, serve_file) -> None:
        result = ActiveCalendarEvent(
            'test', url=serve_file(datadir / 'long-event.ics'), timeout=3,
        ).check()
        assert result is not None
        assert 'long-event' in result

    def test_exact_range(self, datadir, serve_file) -> None:
        with freeze_time('2016-06-05 13:00:00', tz_offset=-2):
            result = ActiveCalendarEvent(
                'test', url=serve_file(datadir / 'long-event.ics'), timeout=3,
            ).check()
            assert result is not None
            assert 'long-event' in result

    def test_before_exact_range(self, datadir, serve_file) -> None:
        with freeze_time('2016-06-05 12:58:00', tz_offset=-2):
            result = ActiveCalendarEvent(
                'test', url=serve_file(datadir / 'long-event.ics'), timeout=3,
            ).check()
            assert result is None

    def test_no_event(self, datadir, serve_file) -> None:
        assert ActiveCalendarEvent(
            'test', url=serve_file(datadir / 'old-event.ics'), timeout=3,
        ).check() is None

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = foobar
                           username = user
                           password = pass
                           timeout = 3''')
        check: ActiveCalendarEvent = ActiveCalendarEvent.create(
            'name', parser['section'],
        )  # type: ignore
        assert check._url == 'foobar'
        assert check._username == 'user'
        assert check._password == 'pass'
        assert check._timeout == 3


class TestActiveConnection(CheckTest):

    MY_PORT = 22
    MY_ADDRESS = '123.456.123.456'
    MY_ADDRESS_IPV6 = 'fe80::5193:518c:5c69:aedb'
    # this might sometimes happen:
    # https://superuser.com/a/99753/227177
    MY_ADDRESS_IPV6_SCOPED = 'fe80::5193:518c:5c69:cccc%eth0'

    def create_instance(self, name):
        return ActiveConnection(name, [10])

    def test_smoke(self) -> None:
        ActiveConnection('foo', [22]).check()

    @pytest.mark.parametrize("connection", [
        # ipv4
        psutil._common.sconn(-1,
                             socket.AF_INET, socket.SOCK_STREAM,
                             (MY_ADDRESS, MY_PORT),
                             ('42.42.42.42', 42),
                             'ESTABLISHED', None),
        # ipv6
        psutil._common.sconn(-1,
                             socket.AF_INET6, socket.SOCK_STREAM,
                             (MY_ADDRESS_IPV6, MY_PORT),
                             ('42.42.42.42', 42),
                             'ESTABLISHED', None),
        # ipv6 where local address has scope
        psutil._common.sconn(-1,
                             socket.AF_INET6, socket.SOCK_STREAM,
                             (MY_ADDRESS_IPV6_SCOPED.split('%')[0], MY_PORT),
                             ('42.42.42.42', 42),
                             'ESTABLISHED', None),
    ])
    def test_connected(self, monkeypatch, connection) -> None:

        def addresses():
            return {
                'dummy': [
                    snic(socket.AF_INET,
                         self.MY_ADDRESS,
                         '255.255.255.0',
                         None, None),
                    snic(socket.AF_INET6,
                         self.MY_ADDRESS_IPV6,
                         'ffff:ffff:ffff:ffff::',
                         None, None),
                    snic(socket.AF_INET6,
                         self.MY_ADDRESS_IPV6_SCOPED,
                         'ffff:ffff:ffff:ffff::',
                         None, None),
                ],
            }

        def connections():
            return [connection]

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
        # not established
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
    def test_not_connected(self, monkeypatch, connection) -> None:

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

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           ports = 10,20,30''')
        assert ActiveConnection.create(
            'name', parser['section'])._ports == {10, 20, 30}

    def test_create_no_entry(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(ConfigurationError):
            ActiveConnection.create('name', parser['section'])

    def test_create_no_number(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           ports = 10,20xx,30''')
        with pytest.raises(ConfigurationError):
            ActiveConnection.create('name', parser['section'])


class TestLoad(CheckTest):

    def create_instance(self, name):
        return Load(name, 0.4)

    def test_below(self, monkeypatch) -> None:

        threshold = 1.34

        def data():
            return [0, threshold - 0.2, 0]
        monkeypatch.setattr(os, 'getloadavg', data)

        assert Load('foo', threshold).check() is None

    def test_above(self, monkeypatch) -> None:

        threshold = 1.34

        def data():
            return [0, threshold + 0.2, 0]
        monkeypatch.setattr(os, 'getloadavg', data)

        assert Load('foo', threshold).check() is not None

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           threshold = 3.2''')
        assert Load.create(
            'name', parser['section'])._threshold == 3.2

    def test_create_no_number(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           threshold = narf''')
        with pytest.raises(ConfigurationError):
            Load.create('name', parser['section'])


class TestMpd(CheckTest):

    def create_instance(self, name):
        return Mpd(name, None, None, None)

    def test_playing(self, monkeypatch) -> None:

        check = Mpd('test', None, None, None)  # type: ignore

        def get_state():
            return {'state': 'play'}
        monkeypatch.setattr(check, '_get_state', get_state)

        assert check.check() is not None

    def test_not_playing(self, monkeypatch) -> None:

        check = Mpd('test', None, None, None)  # type: ignore

        def get_state():
            return {'state': 'pause'}
        monkeypatch.setattr(check, '_get_state', get_state)

        assert check.check() is None

    def test_correct_mpd_interaction(self, mocker) -> None:
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

    def test_handle_connection_errors(self) -> None:

        check = Mpd('test', None, None, None)  # type: ignore

        def _get_state():
            raise ConnectionError()

        check._get_state = _get_state  # type: ignore

        with pytest.raises(TemporaryCheckError):
            check.check()

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           host = host
                           port = 1234
                           timeout = 12''')

        check = Mpd.create('name', parser['section'])

        assert check._host == 'host'
        assert check._port == 1234
        assert check._timeout == 12

    def test_create_port_no_number(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           host = host
                           port = string
                           timeout = 12''')

        with pytest.raises(ConfigurationError):
            Mpd.create('name', parser['section'])

    def test_create_timeout_no_number(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           host = host
                           port = 10
                           timeout = string''')

        with pytest.raises(ConfigurationError):
            Mpd.create('name', parser['section'])


class TestNetworkBandwidth(CheckTest):

    def create_instance(self, name):
        return NetworkBandwidth(name, psutil.net_if_addrs().keys(), 0, 0)

    @staticmethod
    @pytest.fixture()
    def serve_data_url(httpserver) -> str:
        httpserver.expect_request('').respond_with_json({"foo": "bar"})
        return httpserver.url_for('')

    def test_smoke(self, serve_data_url) -> None:
        check = NetworkBandwidth(
            'name', psutil.net_if_addrs().keys(), 0, 0)
        # make some traffic
        requests.get(serve_data_url)
        assert check.check() is not None

    @pytest.fixture
    def mock_interfaces(self, mocker):
        mock = mocker.patch('psutil.net_if_addrs')
        mock.return_value = {'foo': None, 'bar': None, 'baz': None}

    def test_create(self, mock_interfaces) -> None:
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

    def test_create_default(self, mock_interfaces) -> None:
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
    def test_create_error(self, mock_interfaces, config, error_match) -> None:
        parser = configparser.ConfigParser()
        parser.read_string(config)
        with pytest.raises(ConfigurationError, match=error_match):
            NetworkBandwidth.create('name', parser['section'])

    @pytest.mark.parametrize('send_threshold,receive_threshold,match', [
        (sys.float_info.max, 0, 'receive'),
        (0, sys.float_info.max, 'sending'),
    ])
    def test_with_activity(self, send_threshold, receive_threshold, match,
                           serve_data_url) -> None:
        check = NetworkBandwidth(
            'name', psutil.net_if_addrs().keys(),
            send_threshold, receive_threshold)
        # make some traffic
        requests.get(serve_data_url)
        res = check.check()
        assert res is not None
        assert match in res

    def test_no_activity(self, serve_data_url) -> None:
        check = NetworkBandwidth(
            'name', psutil.net_if_addrs().keys(),
            sys.float_info.max, sys.float_info.max)
        # make some traffic
        requests.get(serve_data_url)
        assert check.check() is None

    def test_internal_state_updated(self, serve_data_url) -> None:
        check = NetworkBandwidth(
            'name', psutil.net_if_addrs().keys(),
            sys.float_info.max, sys.float_info.max)
        check.check()
        old_state = check._previous_values
        requests.get(serve_data_url)
        check.check()
        assert old_state != check._previous_values

    def test_delta_calculation_send(self, mocker) -> None:
        first = mocker.MagicMock()
        type(first).bytes_sent = mocker.PropertyMock(return_value=1000)
        type(first).bytes_recv = mocker.PropertyMock(return_value=800)
        mocker.patch('psutil.net_io_counters').return_value = {
            'eth0': first,
        }

        with freeze_time('2019-10-01 10:00:00'):
            check = NetworkBandwidth(
                'name', ['eth0'],
                0, sys.float_info.max,
            )

        second = mocker.MagicMock()
        type(second).bytes_sent = mocker.PropertyMock(return_value=1222)
        type(second).bytes_recv = mocker.PropertyMock(return_value=900)
        mocker.patch('psutil.net_io_counters').return_value = {
            'eth0': second,
        }

        with freeze_time('2019-10-01 10:00:01'):
            res = check.check()
            assert res is not None
            assert ' 222.0 ' in res

    def test_delta_calculation_receive(self, mocker) -> None:
        first = mocker.MagicMock()
        type(first).bytes_sent = mocker.PropertyMock(return_value=1000)
        type(first).bytes_recv = mocker.PropertyMock(return_value=800)
        mocker.patch('psutil.net_io_counters').return_value = {
            'eth0': first,
        }

        with freeze_time('2019-10-01 10:00:00'):
            check = NetworkBandwidth(
                'name', ['eth0'],
                sys.float_info.max, 0,
            )

        second = mocker.MagicMock()
        type(second).bytes_sent = mocker.PropertyMock(return_value=1222)
        type(second).bytes_recv = mocker.PropertyMock(return_value=900)
        mocker.patch('psutil.net_io_counters').return_value = {
            'eth0': second,
        }

        with freeze_time('2019-10-01 10:00:01'):
            res = check.check()
            assert res is not None
            assert ' 100.0 ' in res


class TestKodi(CheckTest):

    def create_instance(self, name):
        return Kodi(name, url='url', timeout=10)

    def test_playing(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1, "jsonrpc": "2.0",
            "result": [{"playerid": 0, "type": "audio"}]}
        mocker.patch('requests.Session.get', return_value=mock_reply)

        assert Kodi('foo', url='url', timeout=10).check() is not None

        mock_reply.json.assert_called_once_with()

    def test_not_playing(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1, "jsonrpc": "2.0", "result": []}
        mocker.patch('requests.Session.get', return_value=mock_reply)

        assert Kodi('foo', url='url', timeout=10).check() is None

        mock_reply.json.assert_called_once_with()

    def test_playing_suspend_while_paused(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1, "jsonrpc": "2.0",
            "result": {"Player.Playing": True}}
        mocker.patch('requests.Session.get', return_value=mock_reply)

        assert Kodi('foo', url='url', timeout=10,
                    suspend_while_paused=True).check() is not None

        mock_reply.json.assert_called_once_with()

    def test_not_playing_suspend_while_paused(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1, "jsonrpc": "2.0",
            "result": {"Player.Playing": False}}
        mocker.patch('requests.Session.get', return_value=mock_reply)

        assert Kodi('foo', url='url', timeout=10,
                    suspend_while_paused=True).check() is None

        mock_reply.json.assert_called_once_with()

    def test_assertion_no_result(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0"}
        mocker.patch('requests.Session.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            Kodi('foo', url='url', timeout=10).check()

    def test_request_error(self, mocker) -> None:
        mocker.patch('requests.Session.get',
                     side_effect=requests.exceptions.RequestException())

        with pytest.raises(TemporaryCheckError):
            Kodi('foo', url='url', timeout=10).check()

    def test_json_error(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.side_effect = json.JSONDecodeError('test', 'test', 42)
        mocker.patch('requests.Session.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            Kodi('foo', url='url', timeout=10).check()

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           timeout = 12''')

        check = Kodi.create('name', parser['section'])

        assert check._url.startswith('anurl')
        assert check._timeout == 12
        assert not check._suspend_while_paused

    def test_create_default_url(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')

        check = Kodi.create('name', parser['section'])

        assert check._url.split('?')[0] == 'http://localhost:8080/jsonrpc'

    def test_create_timeout_no_number(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           timeout = string''')

        with pytest.raises(ConfigurationError):
            Kodi.create('name', parser['section'])

    def test_create_suspend_while_paused(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           suspend_while_paused = True''')

        check = Kodi.create('name', parser['section'])

        assert check._url.startswith('anurl')
        assert check._suspend_while_paused


class TestKodiIdleTime(CheckTest):

    def create_instance(self, name):
        return KodiIdleTime(name, url='url', timeout=10, idle_time=10)

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           timeout = 12
                           idle_time = 42''')

        check = KodiIdleTime.create('name', parser['section'])

        assert check._url.startswith('anurl')
        assert check._timeout == 12
        assert check._idle_time == 42

    def test_create_default_url(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')

        check = KodiIdleTime.create('name', parser['section'])

        assert check._url.split('?')[0] == 'http://localhost:8080/jsonrpc'

    def test_create_timeout_no_number(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           timeout = string''')

        with pytest.raises(ConfigurationError):
            KodiIdleTime.create('name', parser['section'])

    def test_create_idle_time_no_number(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = anurl
                           idle_time = string''')

        with pytest.raises(ConfigurationError):
            KodiIdleTime.create('name', parser['section'])

    def test_no_result(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0"}
        mocker.patch('requests.Session.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime('foo', url='url', timeout=10, idle_time=42).check()

    def test_result_is_list(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0",
                                        "result": []}
        mocker.patch('requests.Session.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime('foo', url='url', timeout=10, idle_time=42).check()

    def test_result_no_entry(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0",
                                        "result": {}}
        mocker.patch('requests.Session.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime('foo', url='url', timeout=10, idle_time=42).check()

    def test_result_wrong_entry(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0",
                                        "result": {"narf": True}}
        mocker.patch('requests.Session.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime('foo', url='url', timeout=10, idle_time=42).check()

    def test_active(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0",
                                        "result": {
                                            "System.IdleTime(42)": False}}
        mocker.patch('requests.Session.get', return_value=mock_reply)

        assert KodiIdleTime('foo', url='url',
                            timeout=10, idle_time=42).check() is not None

    def test_inactive(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0",
                                        "result": {
                                            "System.IdleTime(42)": True}}
        mocker.patch('requests.Session.get', return_value=mock_reply)

        assert KodiIdleTime('foo', url='url',
                            timeout=10, idle_time=42).check() is None

    def test_request_error(self, mocker) -> None:
        mocker.patch('requests.Session.get',
                     side_effect=requests.exceptions.RequestException())

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime('foo', url='url', timeout=10, idle_time=42).check()


class TestPing(CheckTest):

    def create_instance(self, name):
        return Ping(name, '8.8.8.8')

    def test_smoke(self, mocker) -> None:
        mock = mocker.patch('subprocess.call')
        mock.return_value = 1

        hosts = ['abc', '129.123.145.42']

        assert Ping('name', hosts).check() is None

        assert mock.call_count == len(hosts)
        for (args, _), host in zip(mock.call_args_list, hosts):
            assert args[0][-1] == host

    def test_matching(self, mocker) -> None:
        mock = mocker.patch('subprocess.call')
        mock.return_value = 0
        assert Ping('name', ['foo']).check() is not None

    def test_create_missing_hosts(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(ConfigurationError):
            Ping.create('name', parser['section'])

    def test_create_host_splitting(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           hosts=a,b,c''')
        ping = Ping.create('name', parser['section'])
        assert ping._hosts == ['a', 'b', 'c']


class TestXIdleTime(CheckTest):

    def create_instance(self, name):
        return XIdleTime(name, 10, 'sockets', None, None)

    def test_smoke(self, mocker) -> None:
        check = XIdleTime('name', 100, 'logind',
                          re.compile(r'a^'), re.compile(r'a^'))
        mocker.patch.object(check, '_provide_sessions').return_value = [
            ('42', 'auser'),
        ]

        co_mock = mocker.patch('subprocess.check_output')
        co_mock.return_value = '123'

        res = check.check()
        assert res is not None
        assert ' 0.123 ' in res

        args, kwargs = co_mock.call_args
        assert 'auser' in args[0]
        assert kwargs['env']['DISPLAY'] == ':42'
        assert 'auser' in kwargs['env']['XAUTHORITY']

    def test_no_activity(self, mocker) -> None:
        check = XIdleTime('name', 100, 'logind',
                          re.compile(r'a^'), re.compile(r'a^'))
        mocker.patch.object(check, '_provide_sessions').return_value = [
            ('42', 'auser'),
        ]

        mocker.patch('subprocess.check_output').return_value = '120000'

        assert check.check() is None

    def test_multiple_sessions(self, mocker) -> None:
        check = XIdleTime('name', 100, 'logind',
                          re.compile(r'a^'), re.compile(r'a^'))
        mocker.patch.object(check, '_provide_sessions').return_value = [
            ('42', 'auser'), ('17', 'otheruser'),
        ]

        co_mock = mocker.patch('subprocess.check_output')
        co_mock.side_effect = [
            '120000', '123',
        ]

        res = check.check()
        assert res is not None
        assert ' 0.123 ' in res

        assert co_mock.call_count == 2
        # check second call for correct values, not checked before
        args, kwargs = co_mock.call_args_list[1]
        assert 'otheruser' in args[0]
        assert kwargs['env']['DISPLAY'] == ':17'
        assert 'otheruser' in kwargs['env']['XAUTHORITY']

    def test_handle_call_error(self, mocker) -> None:
        check = XIdleTime('name', 100, 'logind',
                          re.compile(r'a^'), re.compile(r'a^'))
        mocker.patch.object(check, '_provide_sessions').return_value = [
            ('42', 'auser'),
        ]

        mocker.patch(
            'subprocess.check_output',
        ).side_effect = subprocess.CalledProcessError(2, 'foo')

        with pytest.raises(TemporaryCheckError):
            check.check()

    def test_create_default(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        check = XIdleTime.create('name', parser['section'])
        assert check._timeout == 600
        assert check._ignore_process_re == re.compile(r'a^')
        assert check._ignore_users_re == re.compile(r'a^')
        assert check._provide_sessions == check._list_sessions_sockets

    def test_create(self) -> None:
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

    def test_create_no_int(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              timeout = string''')
        with pytest.raises(ConfigurationError):
            XIdleTime.create('name', parser['section'])

    def test_create_broken_process_re(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              ignore_if_process = [[a-9]''')
        with pytest.raises(ConfigurationError):
            XIdleTime.create('name', parser['section'])

    def test_create_broken_users_re(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              ignore_users = [[a-9]''')
        with pytest.raises(ConfigurationError):
            XIdleTime.create('name', parser['section'])

    def test_create_unknown_method(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              method = asdfasdf''')
        with pytest.raises(ConfigurationError):
            XIdleTime.create('name', parser['section'])

    def test_list_sessions_logind(self, mocker) -> None:
        mock = mocker.patch('autosuspend.checks.activity.list_logind_sessions')
        mock.return_value = [('c1', {'Name': 'foo'}),
                             ('c2', {'Display': 'asdfasf'}),
                             ('c3', {'Name': 'hello', 'Display': 'nonumber'}),
                             ('c4', {'Name': 'hello', 'Display': '3'})]

        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        check = XIdleTime.create('name', parser['section'])
        assert check._list_sessions_logind() == [(3, 'hello')]

    def test_list_sessions_socket(self, mocker) -> None:
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


class TestExternalCommand(CheckTest):

    def create_instance(self, name):
        return ExternalCommand(name, 'asdfasdf')

    def test_check(self, mocker) -> None:
        mock = mocker.patch('subprocess.check_call')
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              command = foo bar''')
        assert ExternalCommand.create(
            'name', parser['section']).check() is not None  # type: ignore
        mock.assert_called_once_with('foo bar', shell=True)

    def test_check_no_match(self, mocker) -> None:
        mock = mocker.patch('subprocess.check_call')
        mock.side_effect = subprocess.CalledProcessError(2, 'foo bar')
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              command = foo bar''')
        assert ExternalCommand.create(
            'name', parser['section']).check() is None  # type: ignore
        mock.assert_called_once_with('foo bar', shell=True)


class TestXPath(CheckTest):

    def create_instance(self, name):
        return XPath(name=name, url='url', timeout=5,
                     username='userx', password='pass',
                     xpath='/b')

    def test_matching(self, mocker) -> None:
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

    def test_not_matching(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mocker.patch('requests.Session.get', return_value=mock_reply)

        assert XPath('foo', xpath='/b', url='nourl', timeout=5).check() is None

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url = url
                           xpath = /xpath
                           username = user
                           password = pass
                           timeout = 42''')
        check: XPath = XPath.create('name', parser['section'])  # type: ignore
        assert check._xpath == '/xpath'
        assert check._url == 'url'
        assert check._username == 'user'
        assert check._password == 'pass'
        assert check._timeout == 42

    def test_network_errors_are_passed(self, datadir, serve_protected) -> None:
        with pytest.raises(TemporaryCheckError):
            XPath(
                name='name',
                url=serve_protected(datadir / 'data.txt')[0],
                timeout=5, username='wrong', password='wrong',
                xpath='/b',
            ).request()


class TestLogindSessionsIdle(CheckTest):

    def create_instance(self, name):
        return LogindSessionsIdle(
            name, ['tty', 'x11', 'wayland'], ['active', 'online'])

    def test_active(self, logind) -> None:
        logind.AddSession('c1', 'seat0', 1042, 'auser', True)

        check = LogindSessionsIdle(
            'test', ['test'], ['active', 'online'])
        check.check() is not None

    def test_inactive(self, logind) -> None:
        logind.AddSession('c1', 'seat0', 1042, 'auser', False)

        check = LogindSessionsIdle(
            'test', ['test'], ['active', 'online'])
        check.check() is None

    def test_ignore_unknow_type(self, logind) -> None:
        logind.AddSession('c1', 'seat0', 1042, 'auser', True)

        check = LogindSessionsIdle(
            'test', ['not_test'], ['active', 'online'])
        check.check() is None

    def test_configure_defaults(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('[section]')
        check = LogindSessionsIdle.create('name', parser['section'])
        assert check._types == ['tty', 'x11', 'wayland']
        assert check._states == ['active', 'online']

    def test_configure_types(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           types=test, bla,foo''')
        check = LogindSessionsIdle.create('name', parser['section'])
        assert check._types == ['test', 'bla', 'foo']

    def test_configure_states(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           states=test, bla,foo''')
        check = LogindSessionsIdle.create('name', parser['section'])
        assert check._states == ['test', 'bla', 'foo']
