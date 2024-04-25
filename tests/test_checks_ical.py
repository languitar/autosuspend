from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from dateutil import parser
from dateutil.tz import tzlocal
from freezegun import freeze_time

from autosuspend.checks import Check
from autosuspend.checks.ical import (
    ActiveCalendarEvent,
    Calendar,
    CalendarEvent,
    list_calendar_events,
)

from . import CheckTest
from .utils import config_section


class TestCalendarEvent:
    def test_str(self) -> None:
        start = parser.parse("2018-06-11 02:00:00 UTC")
        end = start + timedelta(hours=1)
        event = CalendarEvent("summary", start, end)

        assert "summary" in str(event)


class TestListCalendarEvents:
    def test_simple_recurring(self, datadir: Path) -> None:
        """Tests for basic recurrence.

        Events are collected with the same DST setting as their original
        creation.
        """
        with (datadir / "simple-recurring.ics").open("rb") as f:
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

            expected_end_times = [
                parser.parse("2018-06-18 16:00:00 UTC"),
                parser.parse("2018-06-19 16:00:00 UTC"),
                parser.parse("2018-06-20 16:00:00 UTC"),
                parser.parse("2018-06-21 16:00:00 UTC"),
                parser.parse("2018-06-22 16:00:00 UTC"),
                parser.parse("2018-06-25 16:00:00 UTC"),
                parser.parse("2018-06-26 16:00:00 UTC"),
                parser.parse("2018-06-27 16:00:00 UTC"),
                parser.parse("2018-06-28 16:00:00 UTC"),
                parser.parse("2018-06-29 16:00:00 UTC"),
            ]

            assert expected_start_times == [e.start for e in events]
            assert expected_end_times == [e.end for e in events]

    def test_recurrence_different_dst(self, datadir: Path) -> None:
        with (datadir / "simple-recurring.ics").open("rb") as f:
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

    def test_all_day_events(self, datadir: Path) -> None:
        with (datadir / "all-day-events.ics").open("rb") as f:
            start = parser.parse("2018-06-11 02:00:00 UTC")
            end = start + timedelta(weeks=1)
            events = list_calendar_events(f, start, end)

            assert len(events) == 3
            expected_summaries = ["start", "between", "end"]
            assert [e.summary for e in events] == expected_summaries

    def test_normal_events(self, datadir: Path) -> None:
        with (datadir / "normal-events-corner-cases.ics").open("rb") as f:
            start = parser.parse("2018-06-04 00:00:00 +0200")
            end = start + timedelta(weeks=1)
            events = list_calendar_events(f, start, end)

            expected = [
                (
                    "overlapping",
                    parser.parse("2018-06-02 20:00:00 +0200"),
                    parser.parse("2018-06-12 23:00:00 +0200"),
                ),
                (
                    "before include",
                    parser.parse("2018-06-03 21:00:00 +0200"),
                    parser.parse("2018-06-04 02:00:00 +0200"),
                ),
                (
                    "direct start",
                    parser.parse("2018-06-04 00:00:00 +0200"),
                    parser.parse("2018-06-04 03:00:00 +0200"),
                ),
                (
                    "in between",
                    parser.parse("2018-06-07 04:00:00 +0200"),
                    parser.parse("2018-06-07 09:00:00 +0200"),
                ),
                (
                    "end overlap",
                    parser.parse("2018-06-10 21:00:00 +0200"),
                    parser.parse("2018-06-11 02:00:00 +0200"),
                ),
                (
                    "direct end",
                    parser.parse("2018-06-10 22:00:00 +0200"),
                    parser.parse("2018-06-11 00:00:00 +0200"),
                ),
            ]

            assert [(e.summary, e.start, e.end) for e in events] == expected

    def test_floating_time(self, datadir: Path) -> None:
        with (datadir / "floating.ics").open("rb") as f:
            start = parser.parse("2018-06-09 00:00:00 +0200")
            end = start + timedelta(weeks=1)
            events = list_calendar_events(f, start, end)

            tzinfo = {"LOCAL": tzlocal()}

            expected = [
                (
                    "floating",
                    parser.parse("2018-06-10 15:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-06-10 17:00:00 LOCAL", tzinfos=tzinfo),
                ),
                (
                    "floating recurring",
                    parser.parse("2018-06-12 18:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-06-12 20:00:00 LOCAL", tzinfos=tzinfo),
                ),
                (
                    "floating recurring",
                    parser.parse("2018-06-13 18:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-06-13 20:00:00 LOCAL", tzinfos=tzinfo),
                ),
                (
                    "floating recurring",
                    parser.parse("2018-06-14 18:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-06-14 20:00:00 LOCAL", tzinfos=tzinfo),
                ),
                (
                    "floating recurring",
                    parser.parse("2018-06-15 18:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-06-15 20:00:00 LOCAL", tzinfos=tzinfo),
                ),
            ]

            assert [(e.summary, e.start, e.end) for e in events] == expected

    def test_floating_time_other_dst(self, datadir: Path) -> None:
        with (datadir / "floating.ics").open("rb") as f:
            start = parser.parse("2018-12-09 00:00:00 +0200")
            end = start + timedelta(weeks=1)
            events = list_calendar_events(f, start, end)

            tzinfo = {"LOCAL": tzlocal()}

            expected = [
                (
                    "floating recurring",
                    parser.parse("2018-12-09 18:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-12-09 20:00:00 LOCAL", tzinfos=tzinfo),
                ),
                (
                    "floating recurring",
                    parser.parse("2018-12-10 18:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-12-10 20:00:00 LOCAL", tzinfos=tzinfo),
                ),
                (
                    "floating recurring",
                    parser.parse("2018-12-11 18:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-12-11 20:00:00 LOCAL", tzinfos=tzinfo),
                ),
                (
                    "floating recurring",
                    parser.parse("2018-12-12 18:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-12-12 20:00:00 LOCAL", tzinfos=tzinfo),
                ),
                (
                    "floating recurring",
                    parser.parse("2018-12-13 18:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-12-13 20:00:00 LOCAL", tzinfos=tzinfo),
                ),
                (
                    "floating recurring",
                    parser.parse("2018-12-14 18:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-12-14 20:00:00 LOCAL", tzinfos=tzinfo),
                ),
                (
                    "floating recurring",
                    parser.parse("2018-12-15 18:00:00 LOCAL", tzinfos=tzinfo),
                    parser.parse("2018-12-15 20:00:00 LOCAL", tzinfos=tzinfo),
                ),
            ]

            assert [(e.summary, e.start, e.end) for e in events] == expected

    def test_exclusions(self, datadir: Path) -> None:
        with (datadir / "exclusions.ics").open("rb") as f:
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

    def test_reucrring_single_changes(self, datadir: Path) -> None:
        with (datadir / "single-change.ics").open("rb") as f:
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

    def test_reucrring_change_dst(self, datadir: Path) -> None:
        with (datadir / "recurring-change-dst.ics").open("rb") as f:
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

    def test_recurring_start_and_end_inclusive(self, datadir: Path) -> None:
        with (datadir / "issue-41.ics").open("rb") as f:
            start = parser.parse("2018-06-26 15:13:51 UTC")
            end = start + timedelta(weeks=1)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-06-26 15:00:00 UTC"),
                parser.parse("2018-06-27 15:00:00 UTC"),
                parser.parse("2018-06-28 15:00:00 UTC"),
                parser.parse("2018-06-29 15:00:00 UTC"),
                parser.parse("2018-06-30 15:00:00 UTC"),
                parser.parse("2018-07-01 15:00:00 UTC"),
                parser.parse("2018-07-02 15:00:00 UTC"),
                parser.parse("2018-07-03 15:00:00 UTC"),
            ]

            assert expected_start_times == [e.start for e in events]

    def test_single_start_end_inclusive(self, datadir: Path) -> None:
        with (datadir / "old-event.ics").open("rb") as f:
            start = parser.parse("2004-06-05 11:15:00 UTC")
            end = start + timedelta(hours=1)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2004-06-05 11:00:00 UTC"),
            ]

            assert expected_start_times == [e.start for e in events]

    def test_single_all_day_start_end_inclusive(self, datadir: Path) -> None:
        with (datadir / "all-day-starts.ics").open("rb") as f:
            start = parser.parse("2018-06-25 10:00:00 UTC")
            end = start + timedelta(hours=2)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-06-25 02:00:00 UTC").date(),
            ]

            assert expected_start_times == [e.start for e in events]

            expected_end_times = [
                parser.parse("2018-06-26 02:00:00 UTC").date(),
            ]

            assert expected_end_times == [e.end for e in events]

    def test_longer_single_all_day_start_end_inclusive(self, datadir: Path) -> None:
        with (datadir / "all-day-starts.ics").open("rb") as f:
            start = parser.parse("2018-06-29 10:00:00 UTC")
            end = start + timedelta(hours=2)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-06-28 02:00:00 UTC").date(),
            ]

            assert expected_start_times == [e.start for e in events]

    def test_recurring_all_day_start_end_inclusive(self, datadir: Path) -> None:
        with (datadir / "all-day-recurring.ics").open("rb") as f:
            start = parser.parse("2018-06-29 10:00:00 UTC")
            end = start + timedelta(hours=2)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-06-29 02:00:00 UTC").date(),
            ]

            assert expected_start_times == [e.start for e in events]

            expected_end_times = [
                parser.parse("2018-06-30 02:00:00 UTC").date(),
            ]

            assert expected_end_times == [e.end for e in events]

    def test_recurring_all_day_start_in_between(self, datadir: Path) -> None:
        with (datadir / "all-day-recurring.ics").open("rb") as f:
            start = parser.parse("2018-06-29 00:00:00 UTC")
            end = start + timedelta(days=1)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-06-29 00:00:00 UTC").date(),
                parser.parse("2018-06-30 00:00:00 UTC").date(),
            ]

            assert expected_start_times == [e.start for e in events]

    def test_recurring_all_day_exclusions(self, datadir: Path) -> None:
        with (datadir / "all-day-recurring-exclusions.ics").open("rb") as f:
            start = parser.parse("2018-06-27 00:00:00 UTC")
            end = start + timedelta(days=4)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-06-27 00:00:00 UTC").date(),
                parser.parse("2018-06-28 00:00:00 UTC").date(),
                parser.parse("2018-06-29 00:00:00 UTC").date(),
                parser.parse("2018-07-01 00:00:00 UTC").date(),
            ]

            assert expected_start_times == [e.start for e in events]

    def test_recurring_all_day_exclusions_end(self, datadir: Path) -> None:
        with (datadir / "all-day-recurring-exclusions.ics").open("rb") as f:
            start = parser.parse("2018-06-26 00:00:00 UTC")
            end = start + timedelta(days=4)
            events = list_calendar_events(f, start, end)

            expected_start_times = [
                parser.parse("2018-06-26 00:00:00 UTC").date(),
                parser.parse("2018-06-27 00:00:00 UTC").date(),
                parser.parse("2018-06-28 00:00:00 UTC").date(),
                parser.parse("2018-06-29 00:00:00 UTC").date(),
            ]

            assert expected_start_times == [e.start for e in events]


class TestActiveCalendarEvent(CheckTest):
    def create_instance(self, name: str) -> Check:
        return ActiveCalendarEvent(name, url="asdfasdf", timeout=5)

    def test_smoke(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        result = ActiveCalendarEvent(
            "test",
            url=serve_file(datadir / "long-event.ics"),
            timeout=3,
        ).check()
        assert result is not None
        assert "long-event" in result

    def test_exact_range(
        self, datadir: Path, serve_file: Callable[[Path], str]
    ) -> None:
        with freeze_time("2016-06-05 13:00:00", tz_offset=-2):
            result = ActiveCalendarEvent(
                "test",
                url=serve_file(datadir / "long-event.ics"),
                timeout=3,
            ).check()
            assert result is not None
            assert "long-event" in result

    def test_before_exact_range(
        self, datadir: Path, serve_file: Callable[[Path], str]
    ) -> None:
        with freeze_time("2016-06-05 12:58:00", tz_offset=-2):
            result = ActiveCalendarEvent(
                "test",
                url=serve_file(datadir / "long-event.ics"),
                timeout=3,
            ).check()
            assert result is None

    def test_no_event(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        assert (
            ActiveCalendarEvent(
                "test",
                url=serve_file(datadir / "old-event.ics"),
                timeout=3,
            ).check()
            is None
        )

    def test_create(self) -> None:
        check: ActiveCalendarEvent = ActiveCalendarEvent.create(
            "name",
            config_section(
                {
                    "url": "foobar",
                    "username": "user",
                    "password": "pass",
                    "timeout": "3",
                }
            ),
        )  # type: ignore
        assert check._url == "foobar"
        assert check._username == "user"
        assert check._password == "pass"
        assert check._timeout == 3


class TestCalendar(CheckTest):
    def create_instance(self, name: str) -> Calendar:
        return Calendar(name, url="file:///asdf", timeout=3)

    def test_create(self) -> None:
        section = config_section(
            {
                "url": "url",
                "username": "user",
                "password": "pass",
                "timeout": "42",
            }
        )
        check: Calendar = Calendar.create(
            "name",
            section,
        )  # type: ignore
        assert check._url == "url"
        assert check._username == "user"
        assert check._password == "pass"
        assert check._timeout == 42

    def test_empty(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        timestamp = parser.parse("20050605T130000Z")
        assert (
            Calendar(
                "test",
                url=serve_file(datadir / "old-event.ics"),
                timeout=3,
            ).check(timestamp)
            is None
        )

    def test_smoke(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        timestamp = parser.parse("20040605T090000Z")
        desired_start = parser.parse("20040605T110000Z")

        assert (
            Calendar(
                "test",
                url=serve_file(datadir / "old-event.ics"),
                timeout=3,
            ).check(timestamp)
            == desired_start
        )

    def test_select_earliest(
        self, datadir: Path, serve_file: Callable[[Path], str]
    ) -> None:
        timestamp = parser.parse("20040401T090000Z")
        desired_start = parser.parse("20040405T110000Z")

        assert (
            Calendar(
                "test",
                url=serve_file(datadir / "multiple.ics"),
                timeout=3,
            ).check(timestamp)
            == desired_start
        )

    def test_ignore_running(
        self, datadir: Path, serve_file: Callable[[Path], str]
    ) -> None:
        url = serve_file(datadir / "old-event.ics")
        timestamp = parser.parse("20040605T110000Z")
        # events are taken if start hits exactly the current time
        assert Calendar("test", url=url, timeout=3).check(timestamp) is not None
        timestamp = timestamp + timedelta(seconds=1)
        assert Calendar("test", url=url, timeout=3).check(timestamp) is None

    def test_limited_horizon(
        self, datadir: Path, serve_file: Callable[[Path], str]
    ) -> None:
        timestamp = parser.parse("20040101T000000Z")

        assert (
            Calendar(
                "test",
                url=serve_file(datadir / "after-horizon.ics"),
                timeout=3,
            ).check(timestamp)
            is None
        )

        assert (
            Calendar(
                "test",
                url=serve_file(datadir / "before-horizon.ics"),
                timeout=3,
            ).check(timestamp)
            is not None
        )
