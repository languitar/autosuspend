from datetime import datetime
from typing import Dict, IO, Iterable, List, Mapping

from dateutil.rrule import rruleset, rrulestr
import icalendar
import icalendar.cal
import pytz
import tzlocal


class CalendarEvent(object):

    def __init__(self, summary: str, start: datetime, end: datetime) -> None:
        self.summary = summary
        self.start = start
        self.end = end

    def __str__(self) -> str:
        return 'CalendarEvent[summary={}, start={}, end={}]'.format(
            self.summary, self.start, self.end)


def _expand_rrule(rrule: str,
                  start: datetime,
                  exclusions: Iterable,
                  changes: Iterable[icalendar.cal.Event],
                  start_at: datetime,
                  end_at: datetime):

    # unify everything to a single timezone and then strip it to handle DST
    # changes correctly
    orig_tz = start.tzinfo
    start = start.replace(tzinfo=None)
    start_at = start_at.astimezone(orig_tz).replace(tzinfo=None)
    end_at = end_at.astimezone(orig_tz).replace(tzinfo=None)

    rules = rruleset()
    first_rule = rrulestr(rrule, dtstart=start, ignoretz=True)

    # apply the same timezone logic for the until part of the rule after
    # parsing it.
    if first_rule._until:
        first_rule._until = pytz.utc.localize(
            first_rule._until).astimezone(orig_tz).replace(tzinfo=None)

    rules.rrule(first_rule)

    # add exclusions
    if exclusions:
        if not isinstance(exclusions, list):
            exclusions = [exclusions]
        for xdate in exclusions:
            try:
                # also in this case, unify and strip the timezone
                rules.exdate(
                    xdate.dts[0].dt.astimezone(orig_tz).replace(tzinfo=None))
            except AttributeError:
                pass

    # add events that were changed
    for change in changes:
        # same timezone mangling applies here
        rules.exdate(change.get('recurrence-id').dt.astimezone(
            orig_tz).replace(tzinfo=None))

    # expand the rrule
    dates = []
    for rule in rules.between(start_at, end_at):
        localized = orig_tz.localize(rule)  # noqa: false-positive of mypy
        dates.append(localized)
    return dates


ChangeMapping = Mapping[str, Iterable[icalendar.cal.Event]]


def _collect_recurrence_changes(calendar: icalendar.Calendar)-> ChangeMapping:
    ConcreteChangeMapping = Dict[str, List[icalendar.cal.Event]]  # noqa
    recurring_changes = {}  # type: ConcreteChangeMapping
    for component in calendar.walk():
        if component.name != 'VEVENT':
            continue
        if component.get('recurrence-id'):
            if component.get('uid') not in recurring_changes:
                recurring_changes[component.get('uid')] = []
            recurring_changes[component.get('uid')].append(component)
    return recurring_changes


def list_calendar_events(data: IO[bytes],
                         start_at: datetime,
                         end_at: datetime) -> Iterable[CalendarEvent]:
    """List all relevant calendar events in the provided interval.

    Args:
        data:
            A stream with icalendar data
        start_at:
            include events overlapping with this time (inclusive)
        end_at:
            do not include events that appear after this time or that start
            exactly at this time
    """

    def is_aware(dt: datetime) -> bool:
        return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None

    # some useful notes:
    # * end times and dates are non-inclusive for ical events
    # * start and end are dates for all-day events

    calendar = icalendar.Calendar.from_ical(data.read())

    # Do a first pass through the calendar to collect all exclusions to
    # recurring events so that they can be handled when expanding recurrences.
    recurring_changes = _collect_recurrence_changes(calendar)

    events = []
    for component in calendar.walk():
        if component.name != 'VEVENT':
            continue

        summary = component.get('summary')
        start = component.get('dtstart').dt
        end = component.get('dtend').dt
        exclusions = component.get('exdate')

        # Check whether dates are floating and localize with local time if so.
        # Only works in case of non-all-day events, which are dates, not
        # datetimes.
        if isinstance(start, datetime) and not is_aware(start):
            assert not is_aware(end)
            local_time = tzlocal.get_localzone()
            start = local_time.localize(start)
            end = local_time.localize(end)

        length = end - start

        if component.get('rrule'):
            rrule = component.get('rrule').to_ical().decode('utf-8')
            changes = []  # type: Iterable[icalendar.cal.Event]
            if component.get('uid') in recurring_changes:
                changes = recurring_changes[component.get('uid')]
            for local_start in _expand_rrule(
                    rrule,
                    start,
                    exclusions,
                    changes,
                    start_at,
                    end_at):
                local_end = local_start + length
                events.append(CalendarEvent(summary, local_start, local_end))
        else:
            if isinstance(start, datetime):
                # single events
                if end > start_at and start < end_at:
                    events.append(CalendarEvent(str(summary), start, end))
            else:
                # all-day events
                if end > start_at.date() and start <= end_at.date():
                    events.append(CalendarEvent(str(summary), start, end))

    return sorted(events, key=lambda e: e.start)
