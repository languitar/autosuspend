import datetime
from io import BytesIO
import subprocess

from .util import CommandMixin, NetworkMixin, XPathMixin
from .. import ConfigurationError, TemporaryCheckError, Wakeup


class Calendar(NetworkMixin, Wakeup):
    """Uses an ical calendar to wake up on the next scheduled event."""

    def __init__(self, name: str, **kwargs) -> None:
        NetworkMixin.__init__(self, **kwargs)
        Wakeup.__init__(self, name)

    def check(self, timestamp):
        from ..util.ical import list_calendar_events

        response = self.request()

        end = timestamp + datetime.timedelta(weeks=6 * 4)
        events = list_calendar_events(BytesIO(response.content),
                                      timestamp, end)
        # Filter out currently active events. They are not our business.
        events = [e for e in events if e.start >= timestamp]

        if events:
            return events[0].start


class File(Wakeup):
    """Determines scheduled wake ups from the contents of a file on disk.

    File contents are interpreted as a Unix timestamp in seconds UTC.
    """

    @classmethod
    def create(cls, name, config):
        try:
            path = config['path']
            return cls(name, path)
        except KeyError:
            raise ConfigurationError('Missing option path')

    def __init__(self, name, path):
        Wakeup.__init__(self, name)
        self._path = path

    def check(self, timestamp):
        try:
            with open(self._path, 'r') as time_file:
                return datetime.datetime.fromtimestamp(
                    float(time_file.readlines()[0].strip()),
                    datetime.timezone.utc)
        except FileNotFoundError:
            # this is ok
            pass
        except (ValueError, PermissionError, IOError) as error:
            raise TemporaryCheckError(error)


class Command(CommandMixin, Wakeup):
    """Determine wake up times based on an external command.

    The called command must return a timestamp in UTC or nothing in case no
    wake up is planned.
    """

    def __init__(self, name, command):
        CommandMixin.__init__(self, command)
        Wakeup.__init__(self, name)

    def check(self, timestamp):
        try:
            output = subprocess.check_output(self._command,
                                             shell=True).splitlines()[0]
            self.logger.debug('Command %s succeeded with output %s',
                              self._command, output)
            if output.strip():
                return datetime.datetime.fromtimestamp(
                    float(output.strip()),
                    datetime.timezone.utc)

        except (subprocess.CalledProcessError, ValueError) as error:
            raise TemporaryCheckError(error) from error


class Periodic(Wakeup):
    """Always indicates a wake up after a specified delta of time from now on.

    Use this to periodically wake up a system.
    """

    @classmethod
    def create(cls, name, config):
        try:
            kwargs = {}
            kwargs[config['unit']] = float(config['value'])
            return cls(name, datetime.timedelta(**kwargs))
        except (ValueError, KeyError, TypeError) as error:
            raise ConfigurationError(str(error))

    def __init__(self, name: str, delta: datetime.timedelta) -> None:
        self._delta = delta

    def check(self, timestamp):
        return timestamp + self._delta


class XPath(XPathMixin, Wakeup):
    """Determine wake up times from a network resource using XPath expressions.

    The matched results are expected to represent timestamps in seconds UTC.
    """

    def __init__(self, name, **kwargs):
        Wakeup.__init__(self, name)
        XPathMixin.__init__(self, **kwargs)

    def convert_result(self, result, timestamp):
        return datetime.datetime.fromtimestamp(float(result),
                                               datetime.timezone.utc)

    def check(self, timestamp):
        matches = self.evaluate()
        try:
            if matches:
                return min(self.convert_result(m, timestamp)
                           for m in matches)
        except TypeError as error:
            raise TemporaryCheckError(
                'XPath returned a result that is not a string: ' + str(error))
        except ValueError as error:
            raise TemporaryCheckError('Result cannot be parsed: ' + str(error))


class XPathDelta(XPath):

    UNITS = ['days', 'seconds', 'microseconds', 'milliseconds',
             'minutes', 'hours', 'weeks']

    @classmethod
    def create(cls, name, config):
        try:
            args = XPath.collect_init_args(config)
            args['unit'] = config.get('unit', fallback='minutes')
            return cls(name, **args)
        except ValueError as error:
            raise ConfigurationError(str(error))

    def __init__(self, name, unit, **kwargs):
        if unit not in self.UNITS:
            raise ValueError('Unsupported unit')
        XPath.__init__(self, name, **kwargs)
        self._unit = unit

    def convert_result(self, result, timestamp):
        kwargs = {}
        kwargs[self._unit] = float(result)
        return timestamp + datetime.timedelta(**kwargs)
