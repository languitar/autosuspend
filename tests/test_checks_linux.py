from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path
import re
import socket
import sys
from typing import Any, Mapping

from freezegun import freeze_time
import psutil
import pytest
from pytest_httpserver import HTTPServer
from pytest_mock import MockerFixture
import requests

from autosuspend.checks import (
    Check,
    ConfigurationError,
    SevereCheckError,
    TemporaryCheckError,
)
from autosuspend.checks.linux import (
    ActiveConnection,
    File,
    Load,
    NetworkBandwidth,
    Ping,
    Processes,
    Users,
)

from . import CheckTest
from tests.utils import config_section


class TestUsers(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Users(name, re.compile(".*"), re.compile(".*"), re.compile(".*"))

    @staticmethod
    def create_suser(
        name: str, terminal: str, host: str, started: float, pid: int
    ) -> psutil._common.suser:
        return psutil._common.suser(name, terminal, host, started, pid)

    def test_reports_no_activity_without_users(self, mocker: MockerFixture) -> None:
        mocker.patch("psutil.users").return_value = []

        assert (
            Users("users", re.compile(".*"), re.compile(".*"), re.compile(".*")).check()
            is None
        )

    def test_matching_users(self, mocker: MockerFixture) -> None:
        mocker.patch("psutil.users").return_value = [
            self.create_suser("foo", "pts1", "host", 12345, 12345)
        ]

        assert (
            Users("users", re.compile(".*"), re.compile(".*"), re.compile(".*")).check()
            is not None
        )

    def test_detect_no_activity_if_no_matching_user_exists(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch("psutil.users").return_value = [
            self.create_suser("foo", "pts1", "host", 12345, 12345)
        ]

        assert (
            Users(
                "users", re.compile("narf"), re.compile(".*"), re.compile(".*")
            ).check()
            is None
        )

    class TestCreate:
        def test_it_works_with_a_valid_config(self) -> None:
            check = Users.create(
                "name",
                config_section(
                    {
                        "name": "name.*name",
                        "terminal": "term.*term",
                        "host": "host.*host",
                    }
                ),
            )

            assert check._user_regex == re.compile("name.*name")
            assert check._terminal_regex == re.compile("term.*term")
            assert check._host_regex == re.compile("host.*host")

        def test_raises_with_invalid_expression(self) -> None:
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

    def test_detects_activity_with_matching_process(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch("psutil.process_iter").return_value = [
            self.StubProcess("blubb"),
            self.StubProcess("nonmatching"),
        ]

        assert Processes("foo", ["dummy", "blubb", "other"]).check() is not None

    def test_ignores_no_such_process_errors(self, mocker: MockerFixture) -> None:
        mocker.patch("psutil.process_iter").return_value = [self.RaisingProcess()]

        Processes("foo", ["dummy"]).check()

    def test_detect_no_activity_for_non_matching_processes(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch("psutil.process_iter").return_value = [
            self.StubProcess("asdfasdf"),
            self.StubProcess("nonmatching"),
        ]

        assert Processes("foo", ["dummy", "blubb", "other"]).check() is None

    class TestCreate:
        def test_it_works_with_a_valid_config(self) -> None:
            assert Processes.create(
                "name", config_section({"processes": "foo, bar, narf"})
            )._processes == [
                "foo",
                "bar",
                "narf",
            ]

        def test_raises_if_no_processes_are_configured(self) -> None:
            with pytest.raises(ConfigurationError):
                Processes.create("name", config_section())


snic = namedtuple("snic", ["family", "address", "netmask", "broadcast", "ptp"])


class TestActiveConnection(CheckTest):
    MY_PORT = 22
    MY_ADDRESS = "123.456.123.456"
    MY_ADDRESS_IPV6 = "fe80::5193:518c:5c69:aedb"
    # this might sometimes happen:
    # https://superuser.com/a/99753/227177
    MY_ADDRESS_IPV6_SCOPED = "fe80::5193:518c:5c69:cccc%eth0"

    def create_instance(self, name: str) -> Check:
        return ActiveConnection(name, [10])

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
    def test_detect_activity_if_port_is_connected(
        self, mocker: MockerFixture, connection: psutil._common.sconn
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
    def test_detects_no_activity_if_port_is_not_connected(
        self, mocker: MockerFixture, connection: psutil._common.sconn
    ) -> None:
        mocker.patch("psutil.net_if_addrs").return_value = {
            "dummy": [
                snic(socket.AF_INET, self.MY_ADDRESS, "255.255.255.0", None, None)
            ]
        }
        mocker.patch("psutil.net_connections").return_value = [connection]

        assert ActiveConnection("foo", [10, self.MY_PORT, 30]).check() is None

    class TestCreate:
        def test_it_works_with_a_valid_config(self) -> None:
            assert ActiveConnection.create(
                "name", config_section({"ports": "10,20,30"})
            )._ports == {10, 20, 30}

        def test_raises_if_no_ports_are_configured(self) -> None:
            with pytest.raises(ConfigurationError):
                ActiveConnection.create("name", config_section())

        def test_raises_if_ports_are_not_numeric(self) -> None:
            with pytest.raises(ConfigurationError):
                ActiveConnection.create("name", config_section({"ports": "10,20xx,30"}))


class TestLoad(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Load(name, 0.4)

    def test_detects_no_activity_below_threshold(self, mocker: Any) -> None:
        threshold = 1.34
        mocker.patch("os.getloadavg").return_value = [0, threshold - 0.2, 0]

        assert Load("foo", threshold).check() is None

    def test_detects_activity_above_threshold(self, mocker: MockerFixture) -> None:
        threshold = 1.34
        mocker.patch("os.getloadavg").return_value = [0, threshold + 0.2, 0]

        assert Load("foo", threshold).check() is not None

    class TestCreate:
        def test_it_works_with_a_valid_config(self) -> None:
            assert (
                Load.create("name", config_section({"threshold": "3.2"}))._threshold
                == 3.2
            )

        def test_raises_if_threshold_is_not_numeric(self) -> None:
            with pytest.raises(ConfigurationError):
                Load.create("name", config_section({"threshold": "narf"}))


class TestNetworkBandwidth(CheckTest):
    def create_instance(self, name: str) -> Check:
        return NetworkBandwidth(name, psutil.net_if_addrs().keys(), 0, 0)

    @staticmethod
    @pytest.fixture()
    def serve_data_url(httpserver: HTTPServer) -> str:
        httpserver.expect_request("").respond_with_json({"foo": "bar"})
        return httpserver.url_for("")

    def test_detects_non_mocked_activity(self, serve_data_url: str) -> None:
        check = NetworkBandwidth("name", psutil.net_if_addrs().keys(), 0, 0)
        # make some traffic
        requests.get(serve_data_url, timeout=5)
        assert check.check() is not None

    @pytest.fixture()
    def _mock_interfaces(self, mocker: MockerFixture) -> None:
        mock = mocker.patch("psutil.net_if_addrs")
        mock.return_value = {"foo": None, "bar": None, "baz": None}

    class TestCreate:
        @pytest.mark.usefixtures("_mock_interfaces")
        def test_it_works_with_a_valid_config(self) -> None:
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
        def test_default_values_work(self) -> None:
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
        def test_raises_with_an_invalid_config(
            self, config: Mapping[str, str], error_match: str
        ) -> None:
            with pytest.raises(ConfigurationError, match=error_match):
                NetworkBandwidth.create("name", config_section(config))

    @pytest.mark.parametrize(
        ("send_threshold", "receive_threshold", "match"),
        [(sys.float_info.max, 0, "receive"), (0, sys.float_info.max, "sending")],
    )
    def test_detects_activity_in_direction(
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
        requests.get(serve_data_url, timeout=5)
        res = check.check()
        assert res is not None
        assert match in res

    def test_reports_no_activity_below_threshold(self, serve_data_url: str) -> None:
        check = NetworkBandwidth(
            "name", psutil.net_if_addrs().keys(), sys.float_info.max, sys.float_info.max
        )
        # make some traffic
        requests.get(serve_data_url, timeout=5)
        assert check.check() is None

    def test_internal_state_updating_works(self, serve_data_url: str) -> None:
        check = NetworkBandwidth(
            "name", psutil.net_if_addrs().keys(), sys.float_info.max, sys.float_info.max
        )
        check.check()
        old_state = check._previous_values
        requests.get(serve_data_url, timeout=5)
        check.check()
        assert old_state != check._previous_values

    def test_delta_calculation_send_work(self, mocker: MockerFixture) -> None:
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

    def test_delta_calculation_receive_work(self, mocker: MockerFixture) -> None:
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


class TestPing(CheckTest):
    def create_instance(self, name: str) -> Check:
        return Ping(name, "8.8.8.8")

    def test_calls_ping_correctly(self, mocker: MockerFixture) -> None:
        mock = mocker.patch("subprocess.call")
        mock.return_value = 1

        hosts = ["abc", "129.123.145.42"]

        assert Ping("name", hosts).check() is None

        assert mock.call_count == len(hosts)
        for (args, _), host in zip(mock.call_args_list, hosts):
            assert args[0][-1] == host

    def test_raises_if_the_ping_binary_is_missing(self, mocker: MockerFixture) -> None:
        mock = mocker.patch("subprocess.call")
        mock.side_effect = FileNotFoundError()

        with pytest.raises(SevereCheckError):
            Ping("name", ["test"]).check()

    def test_detect_activity_if_ping_succeeds(self, mocker: MockerFixture) -> None:
        mock = mocker.patch("subprocess.call")
        mock.return_value = 0
        assert Ping("name", ["foo"]).check() is not None

    class TestCreate:
        def test_raises_if_hosts_are_missing(self) -> None:
            with pytest.raises(ConfigurationError):
                Ping.create("name", config_section())

        def test_comma_separated_hosts_are_split(self) -> None:
            ping = Ping.create("name", config_section({"hosts": "a,b,c"}))
            assert ping._hosts == ["a", "b", "c"]


class TestFile(CheckTest):
    def create_instance(self, name: str) -> Check:
        return File(name, Path("asdf"))

    class TestCreate:
        def test_it_works_with_a_valid_config(self) -> None:
            check = File.create("name", config_section({"path": "/tmp/test"}))
            assert check._path == Path("/tmp/test")

        def test_raises_without_path(self) -> None:
            with pytest.raises(ConfigurationError):
                File.create("name", config_section())

    def test_extracts_data_from_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "file"
        test_file.write_text("42\n\n")
        assert File("name", test_file).check(
            datetime.now(timezone.utc)
        ) == datetime.fromtimestamp(42, timezone.utc)

    def test_reports_no_wakeup_if_file_does_not_exist(self, tmp_path: Path) -> None:
        assert File("name", tmp_path / "narf").check(datetime.now(timezone.utc)) is None

    def test_raises_on_permissions_errors(self, tmp_path: Path) -> None:
        file_path = tmp_path / "test"
        file_path.write_bytes(b"2314898")
        file_path.chmod(0)
        with pytest.raises(TemporaryCheckError):
            File("name", file_path).check(datetime.now(timezone.utc))

    def test_raises_on_io_errors(self, tmp_path: Path, mocker: MockerFixture) -> None:
        file_path = tmp_path / "test"
        file_path.write_bytes(b"2314898")
        mocker.patch("pathlib.Path.read_text").side_effect = IOError
        with pytest.raises(TemporaryCheckError):
            File("name", file_path).check(datetime.now(timezone.utc))

    def test_raises_if_file_contents_are_not_a_timestamp(self, tmp_path: Path) -> None:
        test_file = tmp_path / "filexxx"
        test_file.write_text("nonumber\n\n")
        with pytest.raises(TemporaryCheckError):
            File("name", test_file).check(datetime.now(timezone.utc))
