import configparser
from datetime import timedelta
import os.path

from dateutil import parser
from dateutil.tz import tzlocal

import requests

import pytest

from autosuspend.checks import (Activity,
                                ConfigurationError,
                                TemporaryCheckError)
from autosuspend.checks.util import (CalendarEvent,
                                     CommandMixin,
                                     XPathMixin,
                                     list_logind_sessions,
                                     list_calendar_events)


class _CommandMixinSub(CommandMixin, Activity):

    def __init__(self, name, command):
        Activity.__init__(self, name)
        CommandMixin.__init__(self, command)


class TestCommandMixin(object):

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              command = narf bla  ''')
        check = _CommandMixinSub.create('name', parser['section'])
        assert check._command == 'narf bla'

    def test_create_no_command(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(ConfigurationError):
            _CommandMixinSub.create('name', parser['section'])


class _XPathMixinSub(XPathMixin, Activity):

    def __init__(self, name, url, xpath, timeout):
        Activity.__init__(self, name)
        XPathMixin.__init__(self, url, xpath, timeout)


class TestXPathMixin(object):

    @pytest.mark.parametrize('stub_server',
                             [os.path.join(os.path.dirname(__file__),
                                           'test_data')],
                             indirect=True)
    def test_smoke(self, stub_server):
        address = 'http://localhost:{}/xml_with_encoding.xml'.format(
            stub_server.server_address[1])
        _XPathMixinSub('foo', '/b', address, 5).evaluate()

    def test_broken_xml(self, mocker):
        with pytest.raises(TemporaryCheckError):
            mock_reply = mocker.MagicMock()
            content_property = mocker.PropertyMock()
            type(mock_reply).content = content_property
            content_property.return_value = b"//broken"
            mocker.patch('requests.get', return_value=mock_reply)

            _XPathMixinSub('foo', '/b', 'nourl', 5).evaluate()

    def test_xml_with_encoding(self, mocker):
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = \
            b"""<?xml version="1.0" encoding="ISO-8859-1" ?>
<root></root>"""
        mocker.patch('requests.get', return_value=mock_reply)

        _XPathMixinSub('foo', '/b', 'nourl', 5).evaluate()

    def test_xpath_prevalidation(self):
        with pytest.raises(ConfigurationError,
                           match=r'^Invalid xpath.*'):
            parser = configparser.ConfigParser()
            parser.read_string('''[section]
                               xpath=|34/ad
                               url=nourl''')
            _XPathMixinSub.create('name', parser['section'])

    @pytest.mark.parametrize('entry,', ['xpath', 'url'])
    def test_missing_config_entry(self, entry):
        with pytest.raises(ConfigurationError,
                           match=r"^No '" + entry + "'.*"):
            parser = configparser.ConfigParser()
            parser.read_string('''[section]
                               xpath=/valid
                               url=nourl''')
            del parser['section'][entry]
            _XPathMixinSub.create('name', parser['section'])

    def test_create_default_timeout(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           xpath=/valid
                           url=nourl''')
        check = _XPathMixinSub.create('name', parser['section'])
        assert check._timeout == 5

    def test_create_timeout(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           xpath=/valid
                           url=nourl
                           timeout=42''')
        check = _XPathMixinSub.create('name', parser['section'])
        assert check._timeout == 42

    def test_create_invalid_timeout(self):
        with pytest.raises(ConfigurationError,
                           match=r"^Configuration error .*"):
            parser = configparser.ConfigParser()
            parser.read_string('''[section]
                               xpath=/valid
                               url=nourl
                               timeout=xx''')
            _XPathMixinSub.create('name', parser['section'])

    def test_requests_exception(self, mocker):
        with pytest.raises(TemporaryCheckError):
            mock_method = mocker.patch('requests.get')
            mock_method.side_effect = requests.exceptions.ReadTimeout()

            _XPathMixinSub('foo', '/a', 'asdf', 5).evaluate()


def test_list_logind_sessions():
    pytest.importorskip('dbus')

    assert list_logind_sessions() is not None


class TestCalendarEvent(object):

    def test_str(self):
        start = parser.parse("2018-06-11 02:00:00 UTC")
        end = start + timedelta(hours=1)
        event = CalendarEvent('summary', start, end)

        assert 'summary' in str(event)


class TestListCalendarEvents(object):

    def test_simple_recurring(self):
        """Tests for basic recurrence.

        Events are collected with the same DST setting as their original
        creation.
        """
        with open(os.path.join(os.path.dirname(__file__), 'test_data',
                               'simple-recurring.ics'), 'rb') as f:
            start = parser.parse("2018-06-18 04:00:00 UTC")
            end = start + timedelta(weeks=2)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-06-18 07:00:00 UTC"),
                parser.parse("2018-06-19 07:00:00 UTC"),
                parser.parse("2018-06-20 07:00:00 UTC"),
                parser.parse("2018-06-21 07:00:00 UTC"),
                parser.parse("2018-06-22 07:00:00 UTC"),
                parser.parse("2018-06-25 07:00:00 UTC"),
                parser.parse("2018-06-26 07:00:00 UTC"),
                parser.parse("2018-06-27 07:00:00 UTC"),
                parser.parse("2018-06-28 07:00:00 UTC"),
                parser.parse("2018-06-29 07:00:00 UTC"),
            ]

            assert expected_start_times == [e.start for e in events]

    def test_recurrence_different_dst(self):
        with open(os.path.join(os.path.dirname(__file__), 'test_data',
                               'simple-recurring.ics'), 'rb') as f:
            start = parser.parse("2018-11-19 04:00:00 UTC")
            end = start + timedelta(weeks=2)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-11-19 08:00:00 UTC"),
                parser.parse("2018-11-20 08:00:00 UTC"),
                parser.parse("2018-11-21 08:00:00 UTC"),
                parser.parse("2018-11-22 08:00:00 UTC"),
                parser.parse("2018-11-23 08:00:00 UTC"),
                parser.parse("2018-11-26 08:00:00 UTC"),
                parser.parse("2018-11-27 08:00:00 UTC"),
                parser.parse("2018-11-28 08:00:00 UTC"),
                parser.parse("2018-11-29 08:00:00 UTC"),
                parser.parse("2018-11-30 08:00:00 UTC"),
            ]

            assert expected_start_times == [e.start for e in events]

    def test_all_day_events(self):
        with open(os.path.join(os.path.dirname(__file__), 'test_data',
                               'all-day-events.ics'), 'rb') as f:
            start = parser.parse("2018-06-11 02:00:00 UTC")
            end = start + timedelta(weeks=1)
            events = list_calendar_events(f, start, end)

            assert len(events) == 3
            expected_summaries = ['start', 'between', 'end']
            assert [e.summary for e in events] == expected_summaries

    def test_normal_events(self):
        with open(os.path.join(os.path.dirname(__file__), 'test_data',
                               'normal-events-corner-cases.ics'), 'rb') as f:
            start = parser.parse("2018-06-04 00:00:00 +0200")
            end = start + timedelta(weeks=1)
            events = list_calendar_events(f, start, end)

            expected = [
                ('overlapping', parser.parse("2018-06-02 20:00:00 +0200")),
                ('before include', parser.parse("2018-06-03 21:00:00 +0200")),
                ('direct start', parser.parse("2018-06-04 00:00:00 +0200")),
                ('in between', parser.parse("2018-06-07 04:00:00 +0200")),
                ('end overlap', parser.parse("2018-06-10 21:00:00 +0200")),
                ('direct end', parser.parse("2018-06-10 22:00:00 +0200")),
            ]

            assert [(e.summary, e.start) for e in events] == expected

    def test_floating_time(self):
        with open(os.path.join(os.path.dirname(__file__), 'test_data',
                               'floating.ics'), 'rb') as f:
            start = parser.parse("2018-06-09 00:00:00 +0200")
            end = start + timedelta(weeks=1)
            events = list_calendar_events(f, start, end)

            tzinfo = {'LOCAL': tzlocal()}

            expected = [
                ('floating', parser.parse("2018-06-10 15:00:00 LOCAL",
                                          tzinfos=tzinfo)),
                ('floating recurring',
                 parser.parse("2018-06-12 18:00:00 LOCAL", tzinfos=tzinfo)),
                ('floating recurring',
                 parser.parse("2018-06-13 18:00:00 LOCAL", tzinfos=tzinfo)),
                ('floating recurring',
                 parser.parse("2018-06-14 18:00:00 LOCAL", tzinfos=tzinfo)),
                ('floating recurring',
                 parser.parse("2018-06-15 18:00:00 LOCAL", tzinfos=tzinfo)),
            ]

            assert [(e.summary, e.start) for e in events] == expected

    def test_floating_time_other_dst(self):
        with open(os.path.join(os.path.dirname(__file__), 'test_data',
                               'floating.ics'), 'rb') as f:
            start = parser.parse("2018-12-09 00:00:00 +0200")
            end = start + timedelta(weeks=1)
            events = list_calendar_events(f, start, end)

            tzinfo = {'LOCAL': tzlocal()}

            expected = [
                ('floating recurring',
                 parser.parse("2018-12-09 18:00:00 LOCAL", tzinfos=tzinfo)),
                ('floating recurring',
                 parser.parse("2018-12-10 18:00:00 LOCAL", tzinfos=tzinfo)),
                ('floating recurring',
                 parser.parse("2018-12-11 18:00:00 LOCAL", tzinfos=tzinfo)),
                ('floating recurring',
                 parser.parse("2018-12-12 18:00:00 LOCAL", tzinfos=tzinfo)),
                ('floating recurring',
                 parser.parse("2018-12-13 18:00:00 LOCAL", tzinfos=tzinfo)),
                ('floating recurring',
                 parser.parse("2018-12-14 18:00:00 LOCAL", tzinfos=tzinfo)),
                ('floating recurring',
                 parser.parse("2018-12-15 18:00:00 LOCAL", tzinfos=tzinfo)),
            ]

            assert [(e.summary, e.start) for e in events] == expected

    def test_exclusions(self):
        with open(os.path.join(os.path.dirname(__file__), 'test_data',
                               'exclusions.ics'), 'rb') as f:
            start = parser.parse("2018-06-09 04:00:00 UTC")
            end = start + timedelta(weeks=2)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-06-11 12:00:00 UTC"),
                parser.parse("2018-06-12 12:00:00 UTC"),
                parser.parse("2018-06-13 12:00:00 UTC"),
                parser.parse("2018-06-15 12:00:00 UTC"),
                parser.parse("2018-06-16 12:00:00 UTC"),
                parser.parse("2018-06-17 12:00:00 UTC"),
            ]

            assert expected_start_times == [e.start for e in events]

    def test_reucrring_single_changes(self):
        with open(os.path.join(os.path.dirname(__file__), 'test_data',
                               'single-change.ics'), 'rb') as f:
            start = parser.parse("2018-06-11 00:00:00 UTC")
            end = start + timedelta(weeks=1)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-06-11 11:00:00 UTC"),
                parser.parse("2018-06-12 11:00:00 UTC"),
                parser.parse("2018-06-13 14:00:00 UTC"),
                parser.parse("2018-06-14 11:00:00 UTC"),
                parser.parse("2018-06-15 09:00:00 UTC"),
                parser.parse("2018-06-16 11:00:00 UTC"),
                parser.parse("2018-06-17 11:00:00 UTC"),
            ]

            assert expected_start_times == [e.start for e in events]

    def test_reucrring_change_dst(self):
        with open(os.path.join(os.path.dirname(__file__), 'test_data',
                               'recurring-change-dst.ics'), 'rb') as f:
            start = parser.parse("2018-12-10 00:00:00 UTC")
            end = start + timedelta(weeks=1)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-12-10 13:00:00 UTC"),
                parser.parse("2018-12-11 13:00:00 UTC"),
                parser.parse("2018-12-12 10:00:00 UTC"),
                parser.parse("2018-12-13 13:00:00 UTC"),
                parser.parse("2018-12-15 13:00:00 UTC"),
                parser.parse("2018-12-16 13:00:00 UTC"),
            ]

            assert expected_start_times == [e.start for e in events]
