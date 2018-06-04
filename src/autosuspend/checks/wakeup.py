import datetime
import subprocess

from .util import CommandMixin, XPathMixin
from .. import Check, ConfigurationError, TemporaryCheckError, Wakeup


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
        Check.__init__(self, name)
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


class XPath(XPathMixin, Wakeup):
    """Determine wake up times from a network resource using XPath expressions.

    The matched results are expected to represent timestamps in seconds UTC.
    """

    def __init__(self, name, url, xpath, timeout):
        Wakeup.__init__(self, name)
        XPathMixin.__init__(self, url, xpath, timeout)

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
            return super(XPath, cls).create(
                name, config,
                unit=config.get('unit', fallback='minutes'))
        except ValueError as error:
            raise ConfigurationError(str(error))

    def __init__(self, name, url, xpath, timeout, unit='minutes'):
        if unit not in self.UNITS:
            raise ValueError('Unsupported unit')
        XPath.__init__(self, name, url, xpath, timeout)
        self._unit = unit

    def convert_result(self, result, timestamp):
        kwargs = {}
        kwargs[self._unit] = float(result)
        return timestamp + datetime.timedelta(**kwargs)
