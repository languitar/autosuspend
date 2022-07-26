from collections import namedtuple
from datetime import timedelta, timezone
from getpass import getuser
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
from typing import Any, Callable, Dict, Mapping, Tuple

from dbus.proxies import ProxyObject
from freezegun import freeze_time
from jsonpath_ng.ext import parse
import mpd
import psutil
import pytest
from pytest_httpserver import HTTPServer
from pytest_mock import MockFixture
import pytz
import requests

from autosuspend.checks import (
    Check,
    ConfigurationError,
    SevereCheckError,
    TemporaryCheckError,
)
from autosuspend.checks.activity import (
    ActiveConnection,
    ExternalCommand,
    JsonPath,
    Kodi,
    KodiIdleTime,
    LastLogActivity,
    Load,
    LogindSessionsIdle,
    Mpd,
    NetworkBandwidth,
    Ping,
    Processes,
    Smb,
    Users,
    XIdleTime,
    XPath,
)
from autosuspend.util.systemd import LogindDBusException
from autosuspend.util.xorg import (
    list_sessions_logind,
    list_sessions_sockets,
    XorgSession,
)

from . import CheckTest
from tests.utils import config_section


snic = namedtuple("snic", ["family", "address", "netmask", "broadcast", "ptp"])


class TestSmb(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Smb(name)

    def test_no_connections(self, datadir: Path, mocker: MockFixture) -> None:
        mocker.patch("subprocess.check_output").return_value = (
            datadir / "smbstatus_no_connections"
        ).read_bytes()

        assert Smb("foo").check() is None

    def test_with_connections(self, datadir: Path, mocker: MockFixture) -> None:
        mocker.patch("subprocess.check_output").return_value = (
            datadir / "smbstatus_with_connections"
        ).read_bytes()

        res = Smb("foo").check()
        assert res is not None
        assert len(res.splitlines()) == 3

    def test_call_error(self, mocker: MockFixture) -> None:
        mocker.patch(
            "subprocess.check_output",
            side_effect=subprocess.CalledProcessError(2, "cmd"),
        )

        with pytest.raises(TemporaryCheckError):
            Smb("foo").check()

    def test_missing_executable(self, mocker: MockFixture) -> None:
        mocker.patch("subprocess.check_output", side_effect=FileNotFoundError)

        with pytest.raises(SevereCheckError):
            Smb("foo").check()

    def test_create(self) -> None:
        assert isinstance(Smb.create("name", None), Smb)


class TestUsers(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Users(name, re.compile(".*"), re.compile(".*"), re.compile(".*"))

    @staticmethod
    def create_suser(
        name: str, terminal: str, host: str, started: float, pid: int
    ) -> psutil._common.suser:
        return psutil._common.suser(name, terminal, host, started, pid)

    def test_no_users(self, mocker: MockFixture) -> None:
        mocker.patch("psutil.users").return_value = []

        assert (
            Users("users", re.compile(".*"), re.compile(".*"), re.compile(".*")).check()
            is None
        )

    def test_smoke(self) -> None:
        Users("users", re.compile(".*"), re.compile(".*"), re.compile(".*")).check()

    def test_matching_users(self, mocker: MockFixture) -> None:
        mocker.patch("psutil.users").return_value = [
            self.create_suser("foo", "pts1", "host", 12345, 12345)
        ]

        assert (
            Users("users", re.compile(".*"), re.compile(".*"), re.compile(".*")).check()
            is not None
        )

    def test_non_matching_user(self, mocker: MockFixture) -> None:
        mocker.patch("psutil.users").return_value = [
            self.create_suser("foo", "pts1", "host", 12345, 12345)
        ]

        assert (
            Users(
                "users", re.compile("narf"), re.compile(".*"), re.compile(".*")
            ).check()
            is None
        )

    def test_create(self) -> None:
        check = Users.create(
            "name",
            config_section(
                {"name": "name.*name", "terminal": "term.*term", "host": "host.*host"}
            ),
        )

        assert check._user_regex == re.compile("name.*name")
        assert check._terminal_regex == re.compile("term.*term")
        assert check._host_regex == re.compile("host.*host")

    def test_create_regex_error(self) -> None:
        with pytest.raises(ConfigurationError):
            Users.create(
                "name",
                config_section(
                    {
                        "name": "name.*name",
                        "terminal": "term.[[a-9]term",
                        "host": "host.*host",
                    }
                ),
            )


class TestProcesses(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Processes(name, ["foo"])

    class StubProcess:
        def __init__(self, name: str) -> None:
            self._name = name

        def name(self) -> str:
            return self._name

    class RaisingProcess:
        def name(self) -> str:
            raise psutil.NoSuchProcess(42)

    def test_matching_process(self, mocker: MockFixture) -> None:
        mocker.patch("psutil.process_iter").return_value = [
            self.StubProcess("blubb"),
            self.StubProcess("nonmatching"),
        ]

        assert Processes("foo", ["dummy", "blubb", "other"]).check() is not None

    def test_ignore_no_such_process(self, mocker: MockFixture) -> None:
        mocker.patch("psutil.process_iter").return_value = [self.RaisingProcess()]

        Processes("foo", ["dummy"]).check()

    def test_non_matching_process(self, mocker: MockFixture) -> None:
        mocker.patch("psutil.process_iter").return_value = [
            self.StubProcess("asdfasdf"),
            self.StubProcess("nonmatching"),
        ]

        assert Processes("foo", ["dummy", "blubb", "other"]).check() is None

    def test_create(self) -> None:
        assert Processes.create(
            "name", config_section({"processes": "foo, bar, narf"})
        )._processes == [
            "foo",
            "bar",
            "narf",
        ]

    def test_create_no_entry(self) -> None:
        with pytest.raises(ConfigurationError):
            Processes.create("name", config_section())


class TestActiveConnection(CheckTest):

    MY_PORT = 22
    MY_ADDRESS = "123.456.123.456"
    MY_ADDRESS_IPV6 = "fe80::5193:518c:5c69:aedb"
    # this might sometimes happen:
    # https://superuser.com/a/99753/227177
    MY_ADDRESS_IPV6_SCOPED = "fe80::5193:518c:5c69:cccc%eth0"

    def create_instance(self, name: str) -> Check:
        return ActiveConnection(name, [10])

    def test_smoke(self) -> None:
        ActiveConnection("foo", [22]).check()

    @pytest.mark.parametrize(
        "connection",
        [
            # ipv4
            psutil._common.sconn(
                -1,
                socket.AF_INET,
                socket.SOCK_STREAM,
                (MY_ADDRESS, MY_PORT),
                ("42.42.42.42", 42),
                "ESTABLISHED",
                None,
            ),
            # ipv6
            psutil._common.sconn(
                -1,
                socket.AF_INET6,
                socket.SOCK_STREAM,
                (MY_ADDRESS_IPV6, MY_PORT),
                ("42.42.42.42", 42),
                "ESTABLISHED",
                None,
            ),
            # ipv6 where local address has scope
            psutil._common.sconn(
                -1,
                socket.AF_INET6,
                socket.SOCK_STREAM,
                (MY_ADDRESS_IPV6_SCOPED.split("%")[0], MY_PORT),
                ("42.42.42.42", 42),
                "ESTABLISHED",
                None,
            ),
            # ipv6 with mapping to ipv4
            # https://github.com/languitar/autosuspend/issues/116
            psutil._common.sconn(
                -1,
                socket.AF_INET6,
                socket.SOCK_STREAM,
                (f"::ffff:{MY_ADDRESS}", MY_PORT),
                ("42.42.42.42", 42),
                "ESTABLISHED",
                None,
            ),
        ],
    )
    def test_connected(
        self, mocker: MockFixture, connection: psutil._common.sconn
    ) -> None:
        mocker.patch("psutil.net_if_addrs").return_value = {
            "dummy": [
                snic(socket.AF_INET, self.MY_ADDRESS, "255.255.255.0", None, None),
                snic(
                    socket.AF_INET6,
                    self.MY_ADDRESS_IPV6,
                    "ffff:ffff:ffff:ffff::",
                    None,
                    None,
                ),
                snic(
                    socket.AF_INET6,
                    self.MY_ADDRESS_IPV6_SCOPED,
                    "ffff:ffff:ffff:ffff::",
                    None,
                    None,
                ),
            ],
        }
        mocker.patch("psutil.net_connections").return_value = [connection]

        assert ActiveConnection("foo", [10, self.MY_PORT, 30]).check() is not None

    @pytest.mark.parametrize(
        "connection",
        [
            # not my port
            psutil._common.sconn(
                -1,
                socket.AF_INET,
                socket.SOCK_STREAM,
                (MY_ADDRESS, 32),
                ("42.42.42.42", 42),
                "ESTABLISHED",
                None,
            ),
            # not my local address
            psutil._common.sconn(
                -1,
                socket.AF_INET,
                socket.SOCK_STREAM,
                ("33.33.33.33", MY_PORT),
                ("42.42.42.42", 42),
                "ESTABLISHED",
                None,
            ),
            # not established
            psutil._common.sconn(
                -1,
                socket.AF_INET,
                socket.SOCK_STREAM,
                (MY_ADDRESS, MY_PORT),
                ("42.42.42.42", 42),
                "NARF",
                None,
            ),
            # I am the client
            psutil._common.sconn(
                -1,
                socket.AF_INET,
                socket.SOCK_STREAM,
                ("42.42.42.42", 42),
                (MY_ADDRESS, MY_PORT),
                "NARF",
                None,
            ),
        ],
    )
    def test_not_connected(
        self, mocker: MockFixture, connection: psutil._common.sconn
    ) -> None:
        mocker.patch("psutil.net_if_addrs").return_value = {
            "dummy": [
                snic(socket.AF_INET, self.MY_ADDRESS, "255.255.255.0", None, None)
            ]
        }
        mocker.patch("psutil.net_connections").return_value = [connection]

        assert ActiveConnection("foo", [10, self.MY_PORT, 30]).check() is None

    def test_create(self) -> None:
        assert ActiveConnection.create(
            "name", config_section({"ports": "10,20,30"})
        )._ports == {10, 20, 30}

    def test_create_no_entry(self) -> None:
        with pytest.raises(ConfigurationError):
            ActiveConnection.create("name", config_section())

    def test_create_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            ActiveConnection.create("name", config_section({"ports": "10,20xx,30"}))


class TestLoad(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Load(name, 0.4)

    def test_below(self, mocker: Any) -> None:
        threshold = 1.34
        mocker.patch("os.getloadavg").return_value = [0, threshold - 0.2, 0]

        assert Load("foo", threshold).check() is None

    def test_above(self, mocker: MockFixture) -> None:
        threshold = 1.34
        mocker.patch("os.getloadavg").return_value = [0, threshold + 0.2, 0]

        assert Load("foo", threshold).check() is not None

    def test_create(self) -> None:
        assert (
            Load.create("name", config_section({"threshold": "3.2"}))._threshold == 3.2
        )

    def test_create_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            Load.create("name", config_section({"threshold": "narf"}))


class TestMpd(CheckTest):
    def create_instance(self, name: str) -> Check:
        # concrete values are never used in the tests
        return Mpd(name, None, None, None)  # type: ignore

    def test_playing(self, monkeypatch: Any) -> None:

        check = Mpd("test", None, None, None)  # type: ignore

        def get_state() -> Dict:
            return {"state": "play"}

        monkeypatch.setattr(check, "_get_state", get_state)

        assert check.check() is not None

    def test_not_playing(self, monkeypatch: Any) -> None:

        check = Mpd("test", None, None, None)  # type: ignore

        def get_state() -> Dict:
            return {"state": "pause"}

        monkeypatch.setattr(check, "_get_state", get_state)

        assert check.check() is None

    def test_correct_mpd_interaction(self, mocker: MockFixture) -> None:
        import mpd

        mock_instance = mocker.MagicMock(spec=mpd.MPDClient)
        mock_instance.status.return_value = {"state": "play"}
        timeout_property = mocker.PropertyMock()
        type(mock_instance).timeout = timeout_property
        mock = mocker.patch("mpd.MPDClient")
        mock.return_value = mock_instance

        host = "foo"
        port = 42
        timeout = 17

        assert Mpd("name", host, port, timeout).check() is not None

        timeout_property.assert_called_once_with(timeout)
        mock_instance.connect.assert_called_once_with(host, port)
        mock_instance.status.assert_called_once_with()
        mock_instance.close.assert_called_once_with()
        mock_instance.disconnect.assert_called_once_with()

    @pytest.mark.parametrize("exception_type", [ConnectionError, mpd.ConnectionError])
    def test_handle_connection_errors(self, exception_type: type) -> None:

        check = Mpd("test", None, None, None)  # type: ignore

        def _get_state() -> Dict:
            raise exception_type()

        # https://github.com/python/mypy/issues/2427
        check._get_state = _get_state  # type: ignore

        with pytest.raises(TemporaryCheckError):
            check.check()

    def test_create(self) -> None:
        check = Mpd.create(
            "name",
            config_section(
                {
                    "host": "host",
                    "port": "1234",
                    "timeout": "12",
                }
            ),
        )

        assert check._host == "host"
        assert check._port == 1234
        assert check._timeout == 12

    def test_create_port_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            Mpd.create(
                "name",
                config_section(
                    {
                        "host": "host",
                        "port": "string",
                        "timeout": "12",
                    }
                ),
            )

    def test_create_timeout_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            Mpd.create(
                "name",
                config_section(
                    {
                        "host": "host",
                        "port": "10",
                        "timeout": "string",
                    }
                ),
            )


class TestNetworkBandwidth(CheckTest):
    def create_instance(self, name: str) -> Check:
        return NetworkBandwidth(name, psutil.net_if_addrs().keys(), 0, 0)

    @staticmethod
    @pytest.fixture()
    def serve_data_url(httpserver: HTTPServer) -> str:
        httpserver.expect_request("").respond_with_json({"foo": "bar"})
        return httpserver.url_for("")

    def test_smoke(self, serve_data_url: str) -> None:
        check = NetworkBandwidth("name", psutil.net_if_addrs().keys(), 0, 0)
        # make some traffic
        requests.get(serve_data_url)
        assert check.check() is not None

    @pytest.fixture()
    def _mock_interfaces(self, mocker: MockFixture) -> None:
        mock = mocker.patch("psutil.net_if_addrs")
        mock.return_value = {"foo": None, "bar": None, "baz": None}

    @pytest.mark.usefixtures("_mock_interfaces")
    def test_create(self) -> None:
        check = NetworkBandwidth.create(
            "name",
            config_section(
                {
                    "interfaces": "foo, baz",
                    "threshold_send": "200",
                    "threshold_receive": "300",
                }
            ),
        )
        assert set(check._interfaces) == {"foo", "baz"}
        assert check._threshold_send == 200
        assert check._threshold_receive == 300

    @pytest.mark.usefixtures("_mock_interfaces")
    def test_create_default(self) -> None:
        check = NetworkBandwidth.create(
            "name", config_section({"interfaces": "foo, baz"})
        )
        assert set(check._interfaces) == {"foo", "baz"}
        assert check._threshold_send == 100
        assert check._threshold_receive == 100

    @pytest.mark.parametrize(
        ("config", "error_match"),
        [
            (
                {
                    "interfaces": "foo, NOTEXIST",
                    "threshold_send": "200",
                    "threshold_receive": "300",
                },
                r"does not exist",
            ),
            (
                {
                    "threshold_send": "200",
                    "threshold_receive": "300",
                },
                r"configuration key: \'interfaces\'",
            ),
            (
                {
                    "interfaces": "",
                    "threshold_send": "200",
                    "threshold_receive": "300",
                },
                r"No interfaces configured",
            ),
            (
                {
                    "interfaces": "foo, bar",
                    "threshold_send": "xxx",
                },
                r"Threshold in wrong format",
            ),
            (
                {
                    "interfaces": "foo, bar",
                    "threshold_receive": "xxx",
                },
                r"Threshold in wrong format",
            ),
        ],
    )
    @pytest.mark.usefixtures("_mock_interfaces")
    def test_create_error(self, config: Mapping[str, str], error_match: str) -> None:
        with pytest.raises(ConfigurationError, match=error_match):
            NetworkBandwidth.create("name", config_section(config))

    @pytest.mark.parametrize(
        ("send_threshold", "receive_threshold", "match"),
        [(sys.float_info.max, 0, "receive"), (0, sys.float_info.max, "sending")],
    )
    def test_with_activity(
        self,
        send_threshold: float,
        receive_threshold: float,
        match: str,
        serve_data_url: str,
    ) -> None:
        check = NetworkBandwidth(
            "name", psutil.net_if_addrs().keys(), send_threshold, receive_threshold
        )
        # make some traffic
        requests.get(serve_data_url)
        res = check.check()
        assert res is not None
        assert match in res

    def test_no_activity(self, serve_data_url: str) -> None:
        check = NetworkBandwidth(
            "name", psutil.net_if_addrs().keys(), sys.float_info.max, sys.float_info.max
        )
        # make some traffic
        requests.get(serve_data_url)
        assert check.check() is None

    def test_internal_state_updated(self, serve_data_url: str) -> None:
        check = NetworkBandwidth(
            "name", psutil.net_if_addrs().keys(), sys.float_info.max, sys.float_info.max
        )
        check.check()
        old_state = check._previous_values
        requests.get(serve_data_url)
        check.check()
        assert old_state != check._previous_values

    def test_delta_calculation_send(self, mocker: MockFixture) -> None:
        first = mocker.MagicMock()
        type(first).bytes_sent = mocker.PropertyMock(return_value=1000)
        type(first).bytes_recv = mocker.PropertyMock(return_value=800)
        mocker.patch("psutil.net_io_counters").return_value = {
            "eth0": first,
        }

        with freeze_time("2019-10-01 10:00:00"):
            check = NetworkBandwidth("name", ["eth0"], 0, sys.float_info.max)

        second = mocker.MagicMock()
        type(second).bytes_sent = mocker.PropertyMock(return_value=1222)
        type(second).bytes_recv = mocker.PropertyMock(return_value=900)
        mocker.patch("psutil.net_io_counters").return_value = {
            "eth0": second,
        }

        with freeze_time("2019-10-01 10:00:01"):
            res = check.check()
            assert res is not None
            assert " 222.0 " in res

    def test_delta_calculation_receive(self, mocker: MockFixture) -> None:
        first = mocker.MagicMock()
        type(first).bytes_sent = mocker.PropertyMock(return_value=1000)
        type(first).bytes_recv = mocker.PropertyMock(return_value=800)
        mocker.patch("psutil.net_io_counters").return_value = {
            "eth0": first,
        }

        with freeze_time("2019-10-01 10:00:00"):
            check = NetworkBandwidth("name", ["eth0"], sys.float_info.max, 0)

        second = mocker.MagicMock()
        type(second).bytes_sent = mocker.PropertyMock(return_value=1222)
        type(second).bytes_recv = mocker.PropertyMock(return_value=900)
        mocker.patch("psutil.net_io_counters").return_value = {
            "eth0": second,
        }

        with freeze_time("2019-10-01 10:00:01"):
            res = check.check()
            assert res is not None
            assert " 100.0 " in res


class TestKodi(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Kodi(name, url="url", timeout=10)

    def test_playing(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": [{"playerid": 0, "type": "audio"}],
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert Kodi("foo", url="url", timeout=10).check() is not None

        mock_reply.json.assert_called_once_with()

    def test_not_playing(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0", "result": []}
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert Kodi("foo", url="url", timeout=10).check() is None

        mock_reply.json.assert_called_once_with()

    def test_playing_suspend_while_paused(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": {"Player.Playing": True},
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert (
            Kodi("foo", url="url", timeout=10, suspend_while_paused=True).check()
            is not None
        )

        mock_reply.json.assert_called_once_with()

    def test_not_playing_suspend_while_paused(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": {"Player.Playing": False},
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert (
            Kodi("foo", url="url", timeout=10, suspend_while_paused=True).check()
            is None
        )

        mock_reply.json.assert_called_once_with()

    def test_assertion_no_result(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0"}
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            Kodi("foo", url="url", timeout=10).check()

    def test_request_error(self, mocker: MockFixture) -> None:
        mocker.patch(
            "requests.Session.get", side_effect=requests.exceptions.RequestException()
        )

        with pytest.raises(TemporaryCheckError):
            Kodi("foo", url="url", timeout=10).check()

    def test_json_error(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.side_effect = json.JSONDecodeError("test", "test", 42)
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            Kodi("foo", url="url", timeout=10).check()

    def test_create(self) -> None:
        check = Kodi.create(
            "name",
            config_section(
                {
                    "url": "anurl",
                    "timeout": "12",
                }
            ),
        )

        assert check._url.startswith("anurl")
        assert check._timeout == 12
        assert not check._suspend_while_paused

    def test_create_default_url(self) -> None:
        check = Kodi.create("name", config_section())

        assert check._url.split("?")[0] == "http://localhost:8080/jsonrpc"

    def test_create_timeout_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            Kodi.create("name", config_section({"url": "anurl", "timeout": "string"}))

    def test_create_suspend_while_paused(self) -> None:
        check = Kodi.create(
            "name", config_section({"url": "anurl", "suspend_while_paused": "True"})
        )

        assert check._url.startswith("anurl")
        assert check._suspend_while_paused


class TestKodiIdleTime(CheckTest):
    def create_instance(self, name: str) -> Check:
        return KodiIdleTime(name, url="url", timeout=10, idle_time=10)

    def test_create(self) -> None:
        check = KodiIdleTime.create(
            "name", config_section({"url": "anurl", "timeout": "12", "idle_time": "42"})
        )

        assert check._url.startswith("anurl")
        assert check._timeout == 12
        assert check._idle_time == 42

    def test_create_default_url(self) -> None:
        check = KodiIdleTime.create("name", config_section())

        assert check._url.split("?")[0] == "http://localhost:8080/jsonrpc"

    def test_create_timeout_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            KodiIdleTime.create(
                "name", config_section({"url": "anurl", "timeout": "string"})
            )

    def test_create_idle_time_no_number(self) -> None:
        with pytest.raises(ConfigurationError):
            KodiIdleTime.create(
                "name", config_section({"url": "anurl", "idle_time": "string"})
            )

    def test_no_result(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0"}
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check()

    def test_result_is_list(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0", "result": []}
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check()

    def test_result_no_entry(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"id": 1, "jsonrpc": "2.0", "result": {}}
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check()

    def test_result_wrong_entry(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": {"narf": True},
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check()

    def test_active(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": {"System.IdleTime(42)": False},
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert (
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check() is not None
        )

    def test_inactive(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {
            "id": 1,
            "jsonrpc": "2.0",
            "result": {"System.IdleTime(42)": True},
        }
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check() is None

    def test_request_error(self, mocker: MockFixture) -> None:
        mocker.patch(
            "requests.Session.get", side_effect=requests.exceptions.RequestException()
        )

        with pytest.raises(TemporaryCheckError):
            KodiIdleTime("foo", url="url", timeout=10, idle_time=42).check()


class TestPing(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Ping(name, "8.8.8.8")

    def test_smoke(self, mocker: MockFixture) -> None:
        mock = mocker.patch("subprocess.call")
        mock.return_value = 1

        hosts = ["abc", "129.123.145.42"]

        assert Ping("name", hosts).check() is None

        assert mock.call_count == len(hosts)
        for (args, _), host in zip(mock.call_args_list, hosts):
            assert args[0][-1] == host

    def test_missing_ping_binary(self, mocker: MockFixture) -> None:
        mock = mocker.patch("subprocess.call")
        mock.side_effect = FileNotFoundError()

        with pytest.raises(SevereCheckError):
            Ping("name", ["test"]).check()

    def test_matching(self, mocker: MockFixture) -> None:
        mock = mocker.patch("subprocess.call")
        mock.return_value = 0
        assert Ping("name", ["foo"]).check() is not None

    def test_create_missing_hosts(self) -> None:
        with pytest.raises(ConfigurationError):
            Ping.create("name", config_section())

    def test_create_host_splitting(self) -> None:
        ping = Ping.create("name", config_section({"hosts": "a,b,c"}))
        assert ping._hosts == ["a", "b", "c"]


class TestXIdleTime(CheckTest):
    def create_instance(self, name: str) -> Check:
        # concrete values are never used in the test
        return XIdleTime(name, 10, "sockets", None, None)  # type: ignore

    def test_smoke(self, mocker: MockFixture) -> None:
        check = XIdleTime("name", 100, "logind", re.compile(r"a^"), re.compile(r"a^"))
        mocker.patch.object(check, "_provide_sessions").return_value = [
            XorgSession(42, getuser()),
        ]

        co_mock = mocker.patch("subprocess.check_output")
        co_mock.return_value = "123"

        res = check.check()
        assert res is not None
        assert " 0.123 " in res

        args, kwargs = co_mock.call_args
        assert getuser() in args[0]
        assert kwargs["env"]["DISPLAY"] == ":42"
        assert getuser() in kwargs["env"]["XAUTHORITY"]

    def test_no_activity(self, mocker: MockFixture) -> None:
        check = XIdleTime("name", 100, "logind", re.compile(r"a^"), re.compile(r"a^"))
        mocker.patch.object(check, "_provide_sessions").return_value = [
            XorgSession(42, getuser()),
        ]

        mocker.patch("subprocess.check_output").return_value = "120000"

        assert check.check() is None

    def test_multiple_sessions(self, mocker: MockFixture) -> None:
        check = XIdleTime("name", 100, "logind", re.compile(r"a^"), re.compile(r"a^"))
        mocker.patch.object(check, "_provide_sessions").return_value = [
            XorgSession(42, getuser()),
            XorgSession(17, "root"),
        ]

        co_mock = mocker.patch("subprocess.check_output")
        co_mock.side_effect = [
            "120000",
            "123",
        ]

        res = check.check()
        assert res is not None
        assert " 0.123 " in res

        assert co_mock.call_count == 2
        # check second call for correct values, not checked before
        args, kwargs = co_mock.call_args_list[1]
        assert "root" in args[0]
        assert kwargs["env"]["DISPLAY"] == ":17"
        assert "root" in kwargs["env"]["XAUTHORITY"]

    def test_handle_call_error(self, mocker: MockFixture) -> None:
        check = XIdleTime("name", 100, "logind", re.compile(r"a^"), re.compile(r"a^"))
        mocker.patch.object(check, "_provide_sessions").return_value = [
            XorgSession(42, getuser()),
        ]

        mocker.patch(
            "subprocess.check_output",
        ).side_effect = subprocess.CalledProcessError(2, "foo")

        with pytest.raises(TemporaryCheckError):
            check.check()

    def test_create_default(self) -> None:
        check = XIdleTime.create("name", config_section())
        assert check._timeout == 600
        assert check._ignore_process_re == re.compile(r"a^")
        assert check._ignore_users_re == re.compile(r"a^")
        assert check._provide_sessions == list_sessions_sockets

    def test_create(self) -> None:
        check = XIdleTime.create(
            "name",
            config_section(
                {
                    "timeout": "42",
                    "ignore_if_process": ".*test",
                    "ignore_users": "test.*test",
                    "method": "logind",
                }
            ),
        )
        assert check._timeout == 42
        assert check._ignore_process_re == re.compile(r".*test")
        assert check._ignore_users_re == re.compile(r"test.*test")
        assert check._provide_sessions == list_sessions_logind

    def test_create_no_int(self) -> None:
        with pytest.raises(ConfigurationError):
            XIdleTime.create("name", config_section({"timeout": "string"}))

    def test_create_broken_process_re(self) -> None:
        with pytest.raises(ConfigurationError):
            XIdleTime.create("name", config_section({"ignore_if_process": "[[a-9]"}))

    def test_create_broken_users_re(self) -> None:
        with pytest.raises(ConfigurationError):
            XIdleTime.create("name", config_section({"ignore_users": "[[a-9]"}))

    def test_create_unknown_method(self) -> None:
        with pytest.raises(ConfigurationError):
            XIdleTime.create("name", config_section({"method": "asdfasdf"}))

    def test_list_sessions_logind_dbus_error(self, mocker: MockFixture) -> None:
        check = XIdleTime.create("name", config_section())
        mocker.patch.object(
            check, "_provide_sessions"
        ).side_effect = LogindDBusException()

        with pytest.raises(TemporaryCheckError):
            check._safe_provide_sessions()

    def test_sudo_not_found(self, mocker: MockFixture) -> None:
        check = XIdleTime("name", 100, "logind", re.compile(r"a^"), re.compile(r"a^"))
        mocker.patch.object(check, "_provide_sessions").return_value = [
            XorgSession(42, getuser()),
        ]

        mocker.patch("subprocess.check_output").side_effect = FileNotFoundError

        with pytest.raises(SevereCheckError):
            check.check()


class TestExternalCommand(CheckTest):
    def create_instance(self, name: str) -> Check:
        return ExternalCommand(name, "asdfasdf")

    def test_check(self, mocker: MockFixture) -> None:
        mock = mocker.patch("subprocess.check_call")
        assert (
            ExternalCommand.create(
                "name", config_section({"command": "foo bar"})
            ).check()  # type: ignore
            is not None
        )
        mock.assert_called_once_with("foo bar", shell=True)

    def test_check_no_match(self, mocker: MockFixture) -> None:
        mock = mocker.patch("subprocess.check_call")
        mock.side_effect = subprocess.CalledProcessError(2, "foo bar")
        assert (
            ExternalCommand.create("name", config_section({"command": "foo bar"})).check() is None  # type: ignore
        )
        mock.assert_called_once_with("foo bar", shell=True)

    def test_command_not_found(self) -> None:
        with pytest.raises(SevereCheckError):
            ExternalCommand.create(
                "name", config_section({"command": "thisreallydoesnotexist"})
            ).check()  # type: ignore


class TestXPath(CheckTest):
    def create_instance(self, name: str) -> Check:
        return XPath(
            name=name,
            url="url",
            timeout=5,
            username="userx",
            password="pass",
            xpath="/b",
        )

    def test_matching(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mock_method = mocker.patch("requests.Session.get", return_value=mock_reply)

        url = "nourl"
        assert XPath("foo", xpath="/a", url=url, timeout=5).check() is not None

        mock_method.assert_called_once_with(url, timeout=5, headers=None)
        content_property.assert_called_once_with()

    def test_not_matching(self, mocker: MockFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert XPath("foo", xpath="/b", url="nourl", timeout=5).check() is None

    def test_create(self) -> None:
        check: XPath = XPath.create(
            "name",
            config_section(
                {
                    "url": "url",
                    "xpath": "/xpath",
                    "username": "user",
                    "password": "pass",
                    "timeout": "42",
                }
            ),
        )  # type: ignore
        assert check._xpath == "/xpath"
        assert check._url == "url"
        assert check._username == "user"
        assert check._password == "pass"
        assert check._timeout == 42

    def test_network_errors_are_passed(
        self, datadir: Path, serve_protected: Callable[[Path], Tuple[str, str, str]]
    ) -> None:
        with pytest.raises(TemporaryCheckError):
            XPath(
                name="name",
                url=serve_protected(datadir / "data.txt")[0],
                timeout=5,
                username="wrong",
                password="wrong",
                xpath="/b",
            ).request()


class TestLogindSessionsIdle(CheckTest):
    def create_instance(self, name: str) -> Check:
        return LogindSessionsIdle(name, ["tty", "x11", "wayland"], ["active", "online"])

    def test_active(self, logind: ProxyObject) -> None:
        logind.AddSession("c1", "seat0", 1042, "auser", True)

        check = LogindSessionsIdle("test", ["test"], ["active", "online"])
        assert check.check() is not None

    @pytest.mark.skip(reason="No known way to set idle hint in dbus mock right now")
    def test_inactive(self, logind: ProxyObject) -> None:
        logind.AddSession("c1", "seat0", 1042, "auser", False)

        check = LogindSessionsIdle("test", ["test"], ["active", "online"])
        assert check.check() is None

    def test_ignore_unknow_type(self, logind: ProxyObject) -> None:
        logind.AddSession("c1", "seat0", 1042, "auser", True)

        check = LogindSessionsIdle("test", ["not_test"], ["active", "online"])
        assert check.check() is None

    def test_configure_defaults(self) -> None:
        check = LogindSessionsIdle.create("name", config_section())
        assert check._types == ["tty", "x11", "wayland"]
        assert check._states == ["active", "online"]

    def test_configure_types(self) -> None:
        check = LogindSessionsIdle.create(
            "name", config_section({"types": "test, bla,foo"})
        )
        assert check._types == ["test", "bla", "foo"]

    def test_configure_states(self) -> None:
        check = LogindSessionsIdle.create(
            "name", config_section({"states": "test, bla,foo"})
        )
        assert check._states == ["test", "bla", "foo"]

    @pytest.mark.usefixtures("_logind_dbus_error")
    def test_dbus_error(self) -> None:
        check = LogindSessionsIdle("test", ["test"], ["active", "online"])

        with pytest.raises(TemporaryCheckError):
            check.check()


class TestJsonPath(CheckTest):
    def create_instance(self, name: str) -> JsonPath:
        return JsonPath(
            name=name,
            url="url",
            timeout=5,
            username="userx",
            password="pass",
            jsonpath=parse("b"),
        )

    @staticmethod
    @pytest.fixture()
    def json_get_mock(mocker: Any) -> Any:
        mock_reply = mocker.MagicMock()
        mock_reply.json.return_value = {"a": {"b": 42, "c": "ignore"}}
        return mocker.patch("requests.Session.get", return_value=mock_reply)

    def test_matching(self, json_get_mock: Any) -> None:
        url = "nourl"
        assert (
            JsonPath("foo", jsonpath=parse("a.b"), url=url, timeout=5).check()
            is not None
        )

        json_get_mock.assert_called_once_with(
            url, timeout=5, headers={"Accept": "application/json"}
        )
        json_get_mock().json.assert_called_once()

    def test_filter_expressions_work(self, json_get_mock: Any) -> None:
        url = "nourl"
        assert (
            JsonPath(
                "foo", jsonpath=parse("$[?(@.c=='ignore')]"), url=url, timeout=5
            ).check()
            is not None
        )

        json_get_mock.assert_called_once_with(
            url, timeout=5, headers={"Accept": "application/json"}
        )
        json_get_mock().json.assert_called_once()

    def test_not_matching(self, json_get_mock: Any) -> None:
        url = "nourl"
        assert (
            JsonPath("foo", jsonpath=parse("not.there"), url=url, timeout=5).check()
            is None
        )

        json_get_mock.assert_called_once_with(
            url, timeout=5, headers={"Accept": "application/json"}
        )
        json_get_mock().json.assert_called_once()

    def test_network_errors_are_passed(
        self, datadir: Path, serve_protected: Callable[[Path], Tuple[str, str, str]]
    ) -> None:
        with pytest.raises(TemporaryCheckError):
            JsonPath(
                name="name",
                url=serve_protected(datadir / "data.txt")[0],
                timeout=5,
                username="wrong",
                password="wrong",
                jsonpath=parse("b"),
            ).check()

    def test_not_json(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        with pytest.raises(TemporaryCheckError):
            JsonPath(
                name="name",
                url=serve_file(datadir / "invalid.json"),
                timeout=5,
                jsonpath=parse("b"),
            ).check()

    def test_create(self) -> None:
        check: JsonPath = JsonPath.create(
            "name",
            config_section(
                {
                    "url": "url",
                    "jsonpath": "a.b",
                    "username": "user",
                    "password": "pass",
                    "timeout": "42",
                }
            ),
        )  # type: ignore
        assert check._jsonpath == parse("a.b")
        assert check._url == "url"
        assert check._username == "user"
        assert check._password == "pass"
        assert check._timeout == 42

    def test_create_missing_path(self) -> None:
        with pytest.raises(ConfigurationError):
            JsonPath.create(
                "name",
                config_section(
                    {
                        "url": "url",
                        "username": "user",
                        "password": "pass",
                        "timeout": "42",
                    }
                ),
            )

    def test_create_invalid_path(self) -> None:
        with pytest.raises(ConfigurationError):
            JsonPath.create(
                "name",
                config_section(
                    {
                        "url": "url",
                        "jsonpath": ",.asdfjasdklf",
                        "username": "user",
                        "password": "pass",
                        "timeout": "42",
                    }
                ),
            )


class TestLastLogActivity(CheckTest):
    def create_instance(self, name: str) -> LastLogActivity:
        return LastLogActivity(
            name=name,
            log_file=Path("some_file"),
            pattern=re.compile("^(.*)$"),
            delta=timedelta(minutes=10),
            encoding="ascii",
            default_timezone=timezone.utc,
        )

    def test_is_active(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        file_path.write_text("2020-02-02 12:12:23", encoding="ascii")

        with freeze_time("2020-02-02 12:15:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^(.*)$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone.utc,
                ).check()
                is not None
            )

    def test_is_not_active(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        file_path.write_text("2020-02-02 12:12:23", encoding="ascii")

        with freeze_time("2020-02-02 12:35:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^(.*)$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone.utc,
                ).check()
                is None
            )

    def test_uses_last_line(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        # last line is too old and must be used
        file_path.write_text(
            "\n".join(["2020-02-02 12:12:23", "1900-01-01"]), encoding="ascii"
        )

        with freeze_time("2020-02-02 12:15:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^(.*)$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone.utc,
                ).check()
                is None
            )

    def test_ignores_lines_that_do_not_match(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        file_path.write_text("ignored", encoding="ascii")

        assert (
            LastLogActivity(
                "test",
                file_path,
                re.compile(r"^foo(.*)$"),
                timedelta(minutes=10),
                "ascii",
                timezone.utc,
            ).check()
            is None
        )

    def test_uses_pattern(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        file_path.write_text("foo2020-02-02 12:12:23bar", encoding="ascii")

        with freeze_time("2020-02-02 12:15:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^foo(.*)bar$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone.utc,
                ).check()
                is not None
            )

    def test_uses_given_timezone(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        # would match if timezone wasn't used
        file_path.write_text("2020-02-02 12:12:00", encoding="ascii")

        with freeze_time("2020-02-02 12:15:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^(.*)$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone(offset=timedelta(hours=10)),
                ).check()
                is None
            )

    def test_prefers_parsed_timezone(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        # would not match if provided timezone wasn't used
        file_path.write_text("2020-02-02T12:12:01-01:00", encoding="ascii")

        with freeze_time("2020-02-02 13:15:00"):
            assert (
                LastLogActivity(
                    "test",
                    file_path,
                    re.compile(r"^(.*)$"),
                    timedelta(minutes=10),
                    "ascii",
                    timezone.utc,
                ).check()
                is not None
            )

    def test_fails_if_dates_cannot_be_parsed(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        # would match if timezone wasn't used
        file_path.write_text("202000xxx", encoding="ascii")

        with pytest.raises(TemporaryCheckError):
            LastLogActivity(
                "test",
                file_path,
                re.compile(r"^(.*)$"),
                timedelta(minutes=10),
                "ascii",
                timezone.utc,
            ).check()

    def test_fails_if_dates_are_in_the_future(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"
        # would match if timezone wasn't used
        file_path.write_text("2022-01-01", encoding="ascii")

        with freeze_time("2020-02-02 12:15:00"), pytest.raises(TemporaryCheckError):
            LastLogActivity(
                "test",
                file_path,
                re.compile(r"^(.*)$"),
                timedelta(minutes=10),
                "ascii",
                timezone.utc,
            ).check()

    def test_fails_if_file_cannot_be_read(self, tmpdir: Path) -> None:
        file_path = tmpdir / "test.log"

        with pytest.raises(TemporaryCheckError):
            LastLogActivity(
                "test",
                file_path,
                re.compile(r"^(.*)$"),
                timedelta(minutes=10),
                "ascii",
                timezone.utc,
            ).check()

    def test_create(self) -> None:
        created = LastLogActivity.create(
            "thename",
            config_section(
                {
                    "name": "somename",
                    "log_file": "/some/file",
                    "pattern": "^foo(.*)bar$",
                    "minutes": "42",
                    "encoding": "utf-8",
                    "timezone": "Europe/Berlin",
                }
            ),
        )

        assert created.log_file == Path("/some/file")
        assert created.pattern == re.compile(r"^foo(.*)bar$")
        assert created.delta == timedelta(minutes=42)
        assert created.encoding == "utf-8"
        assert created.default_timezone == pytz.timezone("Europe/Berlin")

    def test_create_handles_pattern_errors(self) -> None:
        with pytest.raises(ConfigurationError):
            LastLogActivity.create(
                "thename",
                config_section(
                    {
                        "name": "somename",
                        "log_file": "/some/file",
                        "pattern": "^^foo((.*)bar$",
                    }
                ),
            )

    def test_create_handles_delta_errors(self) -> None:
        with pytest.raises(ConfigurationError):
            LastLogActivity.create(
                "thename",
                config_section(
                    {
                        "name": "somename",
                        "log_file": "/some/file",
                        "pattern": "(.*)",
                        "minutes": "test",
                    }
                ),
            )

    def test_create_handles_negative_deltas(self) -> None:
        with pytest.raises(ConfigurationError):
            LastLogActivity.create(
                "thename",
                config_section(
                    {
                        "name": "somename",
                        "log_file": "/some/file",
                        "pattern": "(.*)",
                        "minutes": "-42",
                    }
                ),
            )

    def test_create_handles_missing_pattern_groups(self) -> None:
        with pytest.raises(ConfigurationError):
            LastLogActivity.create(
                "thename",
                config_section(
                    {
                        "name": "somename",
                        "log_file": "/some/file",
                        "pattern": ".*",
                    }
                ),
            )

    def test_create_handles_missing_keys(self) -> None:
        with pytest.raises(ConfigurationError):
            LastLogActivity.create(
                "thename",
                config_section(
                    {
                        "name": "somename",
                    }
                ),
            )
