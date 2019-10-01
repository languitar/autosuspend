from datetime import date, datetime, timedelta
from typing import Dict, IO, Iterable, List, Mapping, Sequence, Union

from dateutil.rrule import rruleset, rrulestr
import icalendar
import icalendar.cal
import pytz
import tzlocal


class CalendarEvent:

    def __init__(
        self,
        summary: str,
        start: Union[datetime, date],
        end: Union[datetime, date],
    ) -> None:
        self.summary = summary
        self.start = start
        self.end = end

    def __str__(self) -> str:
        return 'CalendarEvent[summary={}, start={}, end={}]'.format(
            self.summary, self.start, self.end)


def _expand_rrule_all_day(rrule: str,
                          start: date,
                          exclusions: Iterable,
                          start_at: datetime,
                          end_at: datetime) -> Iterable[date]:
    """Expand an rrule for all-day events.

    To my mind, these events cannot have changes, just exclusions, because
    changes only affect the time, which doesn't exist for all-day events.
    """

    rules = rruleset()
    rules.rrule(rrulestr(rrule, dtstart=start, ignoretz=True))

    # add exclusions
    if exclusions:
        for xdate in exclusions:
            rules.exdate(datetime.combine(
                xdate.dts[0].dt, datetime.min.time()))

    dates = []
    # reduce start and end to datetimes without timezone that just represent a
    # date at midnight.
    for candidate in rules.between(
            datetime.combine(start_at.date(), datetime.min.time()),
            datetime.combine(end_at.date(), datetime.min.time()),
            inc=True):
        dates.append(candidate.date())
    return dates


def _expand_rrule(rrule: str,
                  start: datetime,
                  instance_duration: timedelta,
                  exclusions: Iterable,
                  changes: Iterable[icalendar.cal.Event],
                  start_at: datetime,
                  end_at: datetime) -> Sequence[datetime]:

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
    for candidate in rules.between(start_at - instance_duration, end_at,
                                   inc=True):
        localized = orig_tz.localize(candidate)  # type: ignore
        dates.append(localized)
    return dates


ChangeMapping = Mapping[str, Iterable[icalendar.cal.Event]]


def _collect_recurrence_changes(calendar: icalendar.Calendar) -> ChangeMapping:
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
                         end_at: datetime) -> Sequence[CalendarEvent]:
    """List all relevant calendar events in the provided interval.

    Args:
        data:
            A stream with icalendar data
        start_at:
            include events overlapping with this time (inclusive)
        end_at:
            do not include events that start after or exactly at this time
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
        if exclusions and not isinstance(exclusions, list):
            exclusions = [exclusions]

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

            if isinstance(start, datetime):
                # complex processing in case of normal events
                for local_start in _expand_rrule(
                        rrule,
                        start,
                        length,
                        exclusions,
                        changes,
                        start_at,
                        end_at):
                    local_end = local_start + length
                    events.append(CalendarEvent(
                        summary, local_start, local_end))
            else:
                # simplified processing for all-day events
                for local_start_date in _expand_rrule_all_day(
                        rrule,
                        start,
                        exclusions,
                        start_at,
                        end_at):
                    local_end = local_start_date + timedelta(days=1)
                    events.append(CalendarEvent(
                        summary, local_start_date, local_end))
        else:
            # same distinction here as above
            if isinstance(start, datetime):
                # single events
                if end > start_at and start < end_at:
                    events.append(CalendarEvent(str(summary), start, end))
            else:
                # all-day events
                if end > start_at.date() and start <= end_at.date():
                    events.append(CalendarEvent(str(summary), start, end))

    return sorted(events, key=lambda e: e.start)
