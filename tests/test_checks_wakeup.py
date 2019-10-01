import configparser
from datetime import datetime, timedelta, timezone
import subprocess

import dateutil.parser
import pytest

from autosuspend.checks import ConfigurationError, TemporaryCheckError
from autosuspend.checks.wakeup import (Calendar,
                                       Command,
                                       File,
                                       Periodic,
                                       XPath,
                                       XPathDelta)
from . import CheckTest


class TestCalendar(CheckTest):

    def create_instance(self, name: str) -> Calendar:
        return Calendar(name, url='file:///asdf', timeout=3)

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              url = url
                              username = user
                              password = pass
                              timeout = 42''')
        check: Calendar = Calendar.create(
            'name', parser['section'],
        )  # type: ignore
        assert check._url == 'url'
        assert check._username == 'user'
        assert check._password == 'pass'
        assert check._timeout == 42

    def test_empty(self, stub_server) -> None:
        address = stub_server.resource_address('old-event.ics')
        timestamp = dateutil.parser.parse('20050605T130000Z')
        assert Calendar(
            'test', url=address, timeout=3).check(timestamp) is None

    def test_smoke(self, stub_server) -> None:
        address = stub_server.resource_address('old-event.ics')
        timestamp = dateutil.parser.parse('20040605T090000Z')
        desired_start = dateutil.parser.parse('20040605T110000Z')

        assert Calendar(
            'test', url=address, timeout=3).check(timestamp) == desired_start

    def test_ignore_running(self, stub_server) -> None:
        address = stub_server.resource_address('old-event.ics')
        timestamp = dateutil.parser.parse('20040605T120000Z')
        assert Calendar(
            'test', url=address, timeout=3).check(timestamp) is None


class TestFile(CheckTest):

    def create_instance(self, name):
        return File(name, 'asdf')

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              path = /tmp/test''')
        check = File.create('name', parser['section'])
        assert check._path == '/tmp/test'

    def test_create_no_path(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(ConfigurationError):
            File.create('name', parser['section'])

    def test_smoke(self, tmpdir) -> None:
        test_file = tmpdir.join('file')
        test_file.write('42\n\n')
        assert File('name', str(test_file)).check(
            datetime.now(timezone.utc)) == datetime.fromtimestamp(
                42, timezone.utc)

    def test_no_file(self, tmpdir) -> None:
        assert File('name', str(tmpdir.join('narf'))).check(
            datetime.now(timezone.utc)) is None

    def test_invalid_number(self, tmpdir) -> None:
        test_file = tmpdir.join('filexxx')
        test_file.write('nonumber\n\n')
        with pytest.raises(TemporaryCheckError):
            File('name', str(test_file)).check(datetime.now(timezone.utc))


class TestCommand(CheckTest):

    def create_instance(self, name):
        return Command(name, 'asdf')

    def test_smoke(self) -> None:
        check = Command('test', 'echo 1234')
        assert check.check(
            datetime.now(timezone.utc)) == datetime.fromtimestamp(
                1234, timezone.utc)

    def test_no_output(self) -> None:
        check = Command('test', 'echo')
        assert check.check(datetime.now(timezone.utc)) is None

    def test_not_parseable(self) -> None:
        check = Command('test', 'echo asdfasdf')
        with pytest.raises(TemporaryCheckError):
            check.check(datetime.now(timezone.utc))

    def test_multiple_lines(self, mocker) -> None:
        mock = mocker.patch('subprocess.check_output')
        mock.return_value = '1234\nignore\n'
        check = Command('test', 'echo bla')
        assert check.check(
            datetime.now(timezone.utc)) == datetime.fromtimestamp(
                1234, timezone.utc)

    def test_multiple_lines_but_empty(self, mocker) -> None:
        mock = mocker.patch('subprocess.check_output')
        mock.return_value = '   \nignore\n'
        check = Command('test', 'echo bla')
        assert check.check(datetime.now(timezone.utc)) is None

    def test_process_error(self, mocker) -> None:
        mock = mocker.patch('subprocess.check_output')
        mock.side_effect = subprocess.CalledProcessError(2, 'foo bar')
        check = Command('test', 'echo bla')
        with pytest.raises(TemporaryCheckError):
            check.check(datetime.now(timezone.utc))


class TestPeriodic(CheckTest):

    def create_instance(self, name):
        delta = timedelta(seconds=10, minutes=42)
        return Periodic(name, delta)

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           unit=seconds
                           value=13''')
        check = Periodic.create('name', parser['section'])
        assert check._delta == timedelta(seconds=13)

    def test_create_wrong_unit(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           unit=asdfasdf
                           value=13''')
        with pytest.raises(ConfigurationError):
            Periodic.create('name', parser['section'])

    def test_create_not_numeric(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           unit=seconds
                           value=asdfasd''')
        with pytest.raises(ConfigurationError):
            Periodic.create('name', parser['section'])

    def test_create_float(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           unit=seconds
                           value=21312.12''')
        Periodic.create('name', parser['section'])

    def test_check(self) -> None:
        delta = timedelta(seconds=10, minutes=42)
        check = Periodic('test', delta)
        now = datetime.now(timezone.utc)
        assert check.check(now) == now + delta


class TestXPath(CheckTest):

    def create_instance(self, name):
        return XPath(name, xpath='/a', url='nourl', timeout=5)

    def test_matching(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = '<a value="42.3"></a>'
        mock_method = mocker.patch('requests.Session.get',
                                   return_value=mock_reply)

        url = 'nourl'
        assert XPath(
            'foo', xpath='/a/@value', url=url, timeout=5).check(
                datetime.now(timezone.utc)) == datetime.fromtimestamp(
                    42.3, timezone.utc)

        mock_method.assert_called_once_with(url, timeout=5)
        content_property.assert_called_once_with()

    def test_not_matching(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mocker.patch('requests.Session.get', return_value=mock_reply)

        assert XPath('foo', xpath='/b', url='nourl', timeout=5).check(
            datetime.now(timezone.utc)) is None

    def test_not_a_string(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mocker.patch('requests.Session.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            XPath('foo', xpath='/a', url='nourl', timeout=5).check(
                datetime.now(timezone.utc))

    def test_not_a_number(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = '<a value="narf"></a>'
        mocker.patch('requests.Session.get', return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            XPath('foo', xpath='/a/@value', url='nourl', timeout=5).check(
                datetime.now(timezone.utc))

    def test_multiple_min(self, mocker) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = '''<root>
    <a value="40"></a>
    <a value="10"></a>
    <a value="20"></a>
</root>
'''
        mocker.patch('requests.Session.get', return_value=mock_reply)

        assert XPath(
            'foo', xpath='//a/@value', url='nourl', timeout=5).check(
                datetime.now(timezone.utc)) == datetime.fromtimestamp(
                    10, timezone.utc)

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           xpath=/valid
                           url=nourl
                           timeout=20''')
        check: XPath = XPath.create('name', parser['section'])  # type: ignore
        assert check._xpath == '/valid'


class TestXPathDelta(CheckTest):

    def create_instance(self, name):
        return XPathDelta(name, xpath='/a', url='nourl', timeout=5,
                          unit='days')

    @pytest.mark.parametrize("unit,factor", [
        ('microseconds', 0.000001),
        ('milliseconds', 0.001),
        ('seconds', 1),
        ('minutes', 60),
        ('hours', 60 * 60),
        ('days', 60 * 60 * 24),
        ('weeks', 60 * 60 * 24 * 7),
    ])
    def test_smoke(self, mocker, unit, factor) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = '<a value="42"></a>'
        mocker.patch('requests.Session.get', return_value=mock_reply)

        url = 'nourl'
        now = datetime.now(timezone.utc)
        result = XPathDelta(
            'foo', xpath='/a/@value', url=url, timeout=5, unit=unit).check(now)
        assert result == now + timedelta(seconds=42) * factor

    def test_create(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           xpath=/valid
                           url=nourl
                           timeout=20
                           unit=weeks''')
        check = XPathDelta.create('name', parser['section'])
        assert check._unit == 'weeks'

    def test_init_wrong_unit(self) -> None:
        with pytest.raises(ValueError):
            XPathDelta('name', url='url', xpath='/a', timeout=5,
                       unit='unknownunit')
