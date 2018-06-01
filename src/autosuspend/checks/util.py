from datetime import datetime
from typing import IO, Iterable, Tuple

from .. import ConfigurationError, TemporaryCheckError


class CommandMixin(object):
    """Mixin for configuring checks based on external commands."""

    @classmethod
    def create(cls, name, config):
        try:
            return cls(name, config['command'].strip())
        except KeyError as error:
            raise ConfigurationError('Missing command specification')

    def __init__(self, command):
        self._command = command


class XPathMixin(object):

    @classmethod
    def create(cls, name, config, **kwargs):
        from lxml import etree
        try:
            xpath = config['xpath'].strip()
            # validate the expression
            try:
                etree.fromstring('<a></a>').xpath(xpath)
            except etree.XPathEvalError:
                raise ConfigurationError('Invalid xpath expression: ' + xpath)
            timeout = config.getint('timeout', fallback=5)
            return cls(name, xpath, config['url'], timeout, **kwargs)
        except ValueError as error:
            raise ConfigurationError('Configuration error ' + str(error))
        except KeyError as error:
            raise ConfigurationError('No ' + str(error) +
                                     ' entry defined for the XPath check')

    def __init__(self, xpath, url, timeout):
        self._xpath = xpath
        self._url = url
        self._timeout = timeout

    def evaluate(self):
        import requests
        import requests.exceptions
        from lxml import etree

        try:
            reply = requests.get(self._url, timeout=self._timeout).content
            root = etree.fromstring(reply)
            return root.xpath(self._xpath)
        except requests.exceptions.RequestException as error:
            raise TemporaryCheckError(error)
        except etree.XMLSyntaxError as error:
            raise TemporaryCheckError(error)


def list_logind_sessions() -> Iterable[Tuple[str, dict]]:
    """List running logind sessions and their properties.

    Returns:
        list of (session_id, properties dict):
            A list with tuples of sessions ids and their associated properties
            represented as dicts.
    """
    import dbus
    bus = dbus.SystemBus()
    login1 = bus.get_object("org.freedesktop.login1",
                            "/org/freedesktop/login1")

    sessions = login1.ListSessions(
        dbus_interface='org.freedesktop.login1.Manager')

    results = []
    for session_id, path in [(s[0], s[4]) for s in sessions]:
        session = bus.get_object('org.freedesktop.login1', path)
        properties_interface = dbus.Interface(
            session, 'org.freedesktop.DBus.Properties')
        properties = properties_interface.GetAll(
            'org.freedesktop.login1.Session')
        results.append((session_id, properties))

    return results


class CalendarEvent(object):

    def __init__(self, summary: str, start: datetime, end: datetime):
        self.summary = summary
        self.start = start
        self.end = end

    def __str__(self) -> str:
        return 'CalendarEvent[summary={}, start={}, end={}]'.format(
            self.summary, self.start, self.end)


def _expand_rrule(rrule: str,
                  start: datetime,
                  exclusions: Iterable,
                  changes: Iterable,
                  start_at: str,
                  end_at: datetime):
    import pytz
    from dateutil.rrule import rruleset, rrulestr

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
        localized = orig_tz.localize(rule)
        dates.append(localized)
    return dates


def _collect_recurrence_changes(calendar):
    recurring_changes = {}
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
    import icalendar
    import tzlocal

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
            changes = []
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
