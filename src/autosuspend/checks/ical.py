from collections.abc import Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from io import BytesIO
from typing import Any, cast, IO, TypeVar

from dateutil.rrule import rrule, rruleset, rrulestr
import icalendar
import icalendar.cal
import pytz
import tzlocal

from . import Activity, Wakeup
from .util import NetworkMixin
from ..util.datetime import is_aware, to_tz_unaware


# Make v6 behave as if it were an older version to support a wider range.
with suppress(AttributeError):
    icalendar.use_pytz()


@dataclass
class CalendarEvent:
    summary: str
    start: datetime | date
    end: datetime | date

    def __str__(self) -> str:
        return (
            f"CalendarEvent[summary={self.summary}, start={self.start}, end={self.end}]"
        )


def _expand_rrule_all_day(
    rrule: str, start: date, exclusions: Iterable, start_at: datetime, end_at: datetime
) -> Iterable[date]:
    """Expand an rrule for all-day events.

    To my mind, these events cannot have changes, just exclusions, because
    changes only affect the time, which doesn't exist for all-day events.
    """
    rules = cast(
        "rruleset", rrulestr(rrule, dtstart=start, ignoretz=True, forceset=True)
    )

    # add exclusions
    if exclusions:
        for xdate in exclusions:
            rules.exdate(datetime.combine(xdate.dts[0].dt, datetime.min.time()))

    dates = []
    # reduce start and end to datetimes without timezone that just represent a
    # date at midnight.
    for candidate in rules.between(
        datetime.combine(start_at.date(), datetime.min.time()),
        datetime.combine(end_at.date(), datetime.min.time()),
        inc=True,
    ):
        dates.append(candidate.date())
    return dates


def _prepare_rruleset_for_expanding(
    rule: str,
    start: datetime,
    exclusions: Iterable,
    changes: Iterable[icalendar.cal.Event],
    tz: tzinfo | None,
) -> rruleset:
    """Prepare an rruleset for expanding.

    Every timestamp is converted to a single timezone and then made unaware to avoid DST
    issues.
    """
    start = to_tz_unaware(start, tz)

    rules = rruleset()
    first_rule = cast(
        "rrule", rrulestr(rule, dtstart=start, ignoretz=True, forceset=False)
    )

    # apply the same timezone logic for the until part of the rule after
    # parsing it.
    if first_rule._until:  # type: ignore
        first_rule._until = to_tz_unaware(  # type: ignore
            pytz.utc.localize(first_rule._until),  # type: ignore
            tz,
        )

    rules.rrule(first_rule)

    # add exclusions
    if exclusions:
        for xdate in exclusions:
            with suppress(AttributeError):
                # also in this case, unify and strip the timezone
                rules.exdate(xdate.dts[0].dt.astimezone(tz).replace(tzinfo=None))

    # add events that were changed
    for change in changes:
        # same timezone mangling applies here
        rules.exdate(to_tz_unaware(change.get("recurrence-id").dt, tz))

    return rules


def _expand_rrule(
    rrule: str,
    start: datetime,
    instance_duration: timedelta,
    exclusions: Iterable,
    changes: Iterable[icalendar.cal.Event],
    start_at: datetime,
    end_at: datetime,
) -> Sequence[datetime]:
    # unify everything to a single timezone and then strip it to handle DST
    # changes correctly
    orig_tz = start.tzinfo
    start_at = to_tz_unaware(start_at, orig_tz)
    end_at = to_tz_unaware(end_at, orig_tz)

    rules = _prepare_rruleset_for_expanding(rrule, start, exclusions, changes, orig_tz)

    # expand the rrule
    dates = []
    for candidate in rules.between(start_at - instance_duration, end_at, inc=True):
        localized = _localize(candidate, orig_tz)
        dates.append(localized)
    return dates


ChangeMapping = dict[str, list[icalendar.cal.Event]]


def _collect_recurrence_changes(calendar: icalendar.Calendar) -> ChangeMapping:
    recurring_changes: ChangeMapping = {}
    for component in calendar.walk("VEVENT"):
        if component.get("recurrence-id"):
            if component.get("uid") not in recurring_changes:
                recurring_changes[component.get("uid")] = []
            recurring_changes[component.get("uid")].append(component)
    return recurring_changes


def _get_recurrence_exclusions_as_list(component: dict) -> list:
    exclusions = component.get("exdate")
    if exclusions and not isinstance(exclusions, list):
        exclusions = [exclusions]
    return exclusions


DateType = TypeVar("DateType", date, datetime)


def _extract_events_from_recurring_component(
    component: icalendar.Event,
    component_start: DateType,
    component_end: DateType,
    start_at: datetime,
    end_at: datetime,
    recurring_changes: ChangeMapping,
) -> list[CalendarEvent]:
    summary = component.get("summary")
    rrule = component.get("rrule").to_ical().decode("utf-8")
    exclusions = _get_recurrence_exclusions_as_list(component)

    length = component_end - component_start

    changes = recurring_changes.get(component.get("uid"), [])

    events = []

    if isinstance(component_start, datetime):
        # complex processing in case of normal events
        for local_start in _expand_rrule(
            rrule, component_start, length, exclusions, changes, start_at, end_at
        ):
            events.append(
                CalendarEvent(str(summary), local_start, local_start + length)
            )
    else:
        # simplified processing for all-day events
        for local_start_date in _expand_rrule_all_day(
            rrule, component_start, exclusions, start_at, end_at
        ):
            events.append(
                CalendarEvent(
                    str(summary), local_start_date, local_start_date + timedelta(days=1)
                )
            )

    return events


def _extract_events_from_single_component(
    component: icalendar.Event,
    component_start: DateType,
    component_end: DateType,
    start_at: datetime,
    end_at: datetime,
) -> list[CalendarEvent]:
    summary = component.get("summary")

    events = []

    # distinction between usual events and all-day events
    if isinstance(component_start, datetime):
        # single events
        if component_end > start_at and component_start < end_at:
            events.append(CalendarEvent(str(summary), component_start, component_end))
    else:
        # all-day events
        if component_end > start_at.date() and component_start <= end_at.date():
            events.append(CalendarEvent(str(summary), component_start, component_end))

    return events


def _localize(dt: datetime, tz: Any) -> datetime:
    """Localizes a datetime with the provided timezone.

    This method handles the different return types of tzlocal in different versions.
    """
    try:
        return tz.localize(dt)
    except AttributeError:
        return dt.astimezone(tz)


def _extract_events_from_component(
    component: icalendar.Event,
    recurring_changes: ChangeMapping,
    start_at: datetime,
    end_at: datetime,
) -> list[CalendarEvent]:
    start = component.get("dtstart").dt
    end = component.get("dtend").dt

    # Check whether dates are floating and localize with local time if so.
    # Only works in case of non-all-day events, which are dates, not
    # datetimes.
    if isinstance(start, datetime) and not is_aware(start):
        assert not is_aware(end)
        local_time = tzlocal.get_localzone()
        start = _localize(start, local_time)
        end = _localize(end, local_time)

    if component.get("rrule"):
        return _extract_events_from_recurring_component(
            component, start, end, start_at, end_at, recurring_changes
        )
    else:
        return _extract_events_from_single_component(
            component, start, end, start_at, end_at
        )


def list_calendar_events(
    data: IO[bytes], start_at: datetime, end_at: datetime
) -> Sequence[CalendarEvent]:
    """List all relevant calendar events in the provided interval.

    Args:
        data:
            A stream with icalendar data
        start_at:
            include events overlapping with this time (inclusive)
        end_at:
            do not include events that start after or exactly at this time
    """
    # some useful notes:
    # * end times and dates are non-inclusive for ical events
    # * start and end are dates for all-day events

    calendar: icalendar.Calendar = icalendar.Calendar.from_ical(data.read())

    # Do a first pass through the calendar to collect all exclusions to
    # recurring events so that they can be handled when expanding recurrences.
    recurring_changes = _collect_recurrence_changes(calendar)

    events = []
    for component in calendar.walk("VEVENT"):
        events.extend(
            _extract_events_from_component(
                component, recurring_changes, start_at, end_at
            )
        )

    return sorted(events, key=lambda e: e.start)


class ActiveCalendarEvent(NetworkMixin, Activity):
    """Determines activity by checking against events in an icalendar file."""

    def __init__(self, name: str, **kwargs: Any) -> None:
        NetworkMixin.__init__(self, **kwargs)
        Activity.__init__(self, name)

    def check(self) -> str | None:
        response = self.request()
        start = datetime.now(timezone.utc)
        end = start + timedelta(minutes=1)
        events = list_calendar_events(BytesIO(response.content), start, end)
        self.logger.debug(
            "Listing active events between %s and %s returned %s events",
            start,
            end,
            len(events),
        )
        if events:
            return f"Calendar event {events[0]} is active"
        else:
            return None


class Calendar(NetworkMixin, Wakeup):
    """Uses an ical calendar to wake up on the next scheduled event."""

    def __init__(self, name: str, **kwargs: Any) -> None:
        NetworkMixin.__init__(self, **kwargs)
        Wakeup.__init__(self, name)

    def check(self, timestamp: datetime) -> datetime | None:
        response = self.request()

        end = timestamp + timedelta(weeks=6 * 4)
        events = list_calendar_events(BytesIO(response.content), timestamp, end)
        # Filter out currently active events. They are not our business.
        events = [e for e in events if e.start >= timestamp]

        if events:
            candidate = events[0]
            if isinstance(candidate.start, datetime):
                return candidate.start
            else:
                return datetime.combine(candidate.start, datetime.min.time())
        else:
            return None
