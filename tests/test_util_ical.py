from datetime import timedelta
import os.path

from dateutil import parser
from dateutil.tz import tzlocal

from autosuspend.util.ical import CalendarEvent, list_calendar_events


class TestCalendarEvent:

    def test_str(self):
        start = parser.parse("2018-06-11 02:00:00 UTC")
        end = start + timedelta(hours=1)
        event = CalendarEvent('summary', start, end)

        assert 'summary' in str(event)


class TestListCalendarEvents:

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
