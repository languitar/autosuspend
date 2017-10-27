#!/usr/bin/env python3

import abc
import argparse
import configparser
import copy
import functools
import glob
import json
import logging
import logging.config
import os
import pwd
import re
import socket
import subprocess
import sys
import time

import psutil


# pylint: disable=invalid-name
_logger = logging.getLogger()
# pylint: enable=invalid-name


class ConfigurationError(RuntimeError):
    """
    Indicates an error in the configuration of a :class:`Check`.
    """
    pass


class TemporaryCheckError(RuntimeError):
    """
    Indicates a temporary error while performing a check which can be ignored
    for some time since it might recover automatically.
    """
    pass


class SevereCheckError(RuntimeError):
    """
    Indicates that a check cannot be executed correctly and there is no hope
    this situation recovers.
    """
    pass


class Check(object):
    """
    Base class for checks.

    Subclasses must call this class' __init__ method.
    """

    @classmethod
    @abc.abstractmethod
    def create(cls, name, config):
        """
        Factory method to create an appropriate instance of the check for the
        provided options.

        Args:
            name (str):
                user-defined name for the check
            config (configparser.SectionProxy):
                config parser section with the configuration for this check

        Raises:
            ConfigurationError:
                Configuration for this check is inappropriate
        """
        pass

    def __init__(self, name=None):
        if name:
            self.name = name
        else:
            self.name = self.__class__.__name__
        self.logger = logging.getLogger(
            'check.{}'.format(self.name))

    @abc.abstractmethod
    def check(self):
        """
        Performs a check and reports whether suspending shall NOT take place.

        Returns:
            str:
                A string describing which condition currently prevents sleep,
                else ``None``.

        Raises:
            TemporaryCheckError:
                Check execution currently fails but might recover later
            SevereCheckError:
                Check executions fails severely
        """
        pass

    def __str__(self):
        return '{name}[class={clazz}]'.format(name=self.name,
                                              clazz=self.__class__.__name__)


class Ping(Check):
    """
    Prevents system sleep in case one or several hosts are reachable via ping.
    """

    @classmethod
    def create(cls, name, config):
        try:
            hosts = config['hosts'].split(',')
            hosts = [h.strip() for h in hosts]
            return cls(name, hosts)
        except KeyError as error:
            raise ConfigurationError(
                'Unable to determine hosts to ping: {}'.format(error))

    def __init__(self, name, hosts):
        Check.__init__(self, name)
        self._hosts = hosts

    def check(self):
        for host in self._hosts:
            cmd = ['ping', '-q', '-c', '1', host]
            if subprocess.call(cmd,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL) == 0:
                self.logger.debug("host " + host + " appears to be up")
                return 'Host {} is up'.format(host)
        return None


class Mpd(Check):

    @classmethod
    def create(cls, name, config):
        try:
            host = config.get('host', fallback='localhost')
            port = config.getint('port', fallback=6600)
            timeout = config.getint('timeout', fallback=5)
            return cls(name, host, port, timeout)
        except ValueError as error:
            raise ConfigurationError(
                'Host port or timeout configuration wrong: {}'.format(error))

    def __init__(self, name, host, port, timeout):
        Check.__init__(self, name)
        self._host = host
        self._port = port
        self._timeout = timeout

    def _get_state(self):
        from mpd import MPDClient
        client = MPDClient()
        client.timeout = self._timeout
        client.connect(self._host, self._port)
        state = client.status()
        client.close()
        client.disconnect()
        return state

    def check(self):
        try:
            state = self._get_state()
            if state['state'] == 'play':
                return 'MPD currently playing'
            else:
                return None
        except (ConnectionError,
                ConnectionRefusedError,
                socket.timeout,
                socket.gaierror) as error:
            raise TemporaryCheckError(error)


class Kodi(Check):

    @classmethod
    def create(cls, name, config):
        try:
            url = config.get('url', fallback='http://localhost:8080/jsonrpc')
            timeout = config.getint('timeout', fallback=5)
            return cls(name, url, timeout)
        except ValueError as error:
            raise ConfigurationError(
                'Url or timeout configuration wrong: {}'.format(error))

    def __init__(self, name, url, timeout):
        Check.__init__(self, name)
        self._url = url
        self._timeout = timeout

    def check(self):
        import requests
        import requests.exceptions

        try:
            reply = requests.get(self._url +
                                 '?request={"jsonrpc": "2.0", '
                                 '"id": 1, '
                                 '"method": "Player.GetActivePlayers"}').json()
            if 'result' not in reply:
                raise TemporaryCheckError('No result array in reply')
            if reply['result']:
                return "Kodi currently playing"
            else:
                return None
        except requests.exceptions.RequestException as error:
            raise TemporaryCheckError(error)


class Users(Check):

    @classmethod
    def create(cls, name, config):
        try:
            user_regex = re.compile(
                config.get('name', fallback='.*'))
            terminal_regex = re.compile(
                config.get('terminal', fallback='.*'))
            host_regex = re.compile(
                config.get('host', fallback='.*'))
            return cls(name, user_regex, terminal_regex, host_regex)
        except re.error as error:
            raise ConfigurationError(
                'Regular expression is invalid: {}'.format(error))

    def __init__(self, name, user_regex, terminal_regex, host_regex):
        Check.__init__(self, name)
        self._user_regex = user_regex
        self._terminal_regex = terminal_regex
        self._host_regex = host_regex

    def check(self):
        for entry in psutil.users():
            if self._user_regex.fullmatch(entry.name) is not None and \
                    self._terminal_regex.fullmatch(
                        entry.terminal) is not None and \
                    self._host_regex.fullmatch(entry.host) is not None:
                self.logger.debug('User %s on terminal %s from host %s '
                                  'matches criteria.', entry.name,
                                  entry.terminal, entry.host)
                return 'User {user} is logged in on terminal {terminal} ' \
                    'from {host} since {started}'.format(
                        user=entry.name, terminal=entry.terminal,
                        host=entry.host, started=entry.started)
        return None


class Smb(Check):

    @classmethod
    def create(cls, name, config):
        return cls(name)

    def check(self):
        try:
            status_output = subprocess.check_output(
                ['smbstatus', '-b']).decode('utf-8')
        except subprocess.CalledProcessError as error:
            raise SevereCheckError(error)

        self.logger.debug('Received status output:\n%s',
                          status_output)

        connections = []
        start_seen = False
        for line in status_output.splitlines():
            if start_seen:
                connections.append(line)
            else:
                if line.startswith('----'):
                    start_seen = True

        if connections:
            return 'SMB clients are connected:\n{}'.format(
                '\n'.join(connections))
        else:
            return None


class Processes(Check):

    @classmethod
    def create(cls, name, config):
        try:
            processes = config['processes'].split(',')
            processes = [p.strip() for p in processes]
            return cls(name, processes)
        except KeyError:
            raise ConfigurationError('No processes to check specified')

    def __init__(self, name, processes):
        Check.__init__(self, name)
        self._processes = processes

    def check(self):
        for proc in psutil.process_iter():
            try:
                pinfo = proc.name()
                for name in self._processes:
                    if pinfo == name:
                        return 'Process {} is running'.format(name)
            except psutil.NoSuchProcess:
                pass
        return None


class ActiveConnection(Check):

    @classmethod
    def create(cls, name, config):
        try:
            ports = config['ports']
            ports = ports.split(',')
            ports = [p.strip() for p in ports]
            ports = set([int(p) for p in ports])
            return cls(name, ports)
        except KeyError:
            raise ConfigurationError('Missing option ports')
        except ValueError:
            raise ConfigurationError('Ports must be integers')

    def __init__(self, name, ports):
        Check.__init__(self, name)
        self._ports = ports

    def check(self):
        own_addresses = [(item.family, item.address)
                         for sublist in psutil.net_if_addrs().values()
                         for item in sublist]
        connected = [c.laddr.port
                     for c in psutil.net_connections()
                     if ((c.family, c.laddr.ip) in own_addresses
                         and c.status == 'ESTABLISHED'
                         and c.laddr.port in self._ports)]
        if connected:
            return 'Ports {} are connected'.format(connected)


class Load(Check):

    @classmethod
    def create(cls, name, config):
        try:
            return cls(name,
                       config.getfloat('threshold', fallback=2.5))
        except ValueError as error:
            raise ConfigurationError(
                'Unable to parse threshold as float: {}'.format(error))

    def __init__(self, name, threshold):
        Check.__init__(self, name)
        self._threshold = threshold

    def check(self):
        loadcurrent = os.getloadavg()[1]
        self.logger.debug("Load: %s", loadcurrent)
        if loadcurrent > self._threshold:
            return 'Load {} > threshold {}'.format(loadcurrent,
                                                   self._threshold)
        else:
            return None


class XIdleTime(Check):
    '''
    Checks users with a local X display have been idle for a sufficiently long
    time.
    '''

    @classmethod
    def create(cls, name, config):
        try:
            return cls(name, config.getint('timeout', fallback=600),
                       re.compile(config.get('ignore_if_process',
                                             fallback=r'a^')),
                       re.compile(config.get('ignore_users',
                                             fallback=r'^a')))
        except re.error as error:
            raise ConfigurationError(
                'Regular expression is invalid: {}'.format(error))
        except ValueError as error:
            raise ConfigurationError(
                'Unable to parse timeout as int: {}'.format(error))

    def __init__(self, name, timeout, ignore_process_re, ignore_users_re):
        Check.__init__(self, name)
        self._timeout = timeout
        self._ignore_process_re = ignore_process_re
        self._ignore_users_re = ignore_users_re

    def check(self):
        sockets = glob.glob('/tmp/.X11-unix/X*')
        self.logger.debug('Found sockets: %s', sockets)
        for sock in sockets:
            self.logger.info('Checking socket %s', sock)

            # determine the number of the X display
            try:
                number = int(sock[len('/tmp/.X11-unix/X'):])
            except ValueError as error:
                self.logger.warning(
                    'Cannot parse display number from socket %s. Skipping.',
                    sock, exc_info=True)
                continue

            # determine the user of the display
            try:
                user = pwd.getpwuid(os.stat(sock).st_uid).pw_name
            except (FileNotFoundError, KeyError) as error:
                self.logger.warning(
                    'Cannot get the owning user from socket %s. Skipping.',
                    sock, exc_info=True)
                continue

            # check whether this users should be ignored completely
            if self._ignore_users_re.match(user) is not None:
                self.logger.debug("Skipping user '%s' due to request", user)
                continue

            # check whether any of the running processes of this user matches
            # the ignore regular expression. In that case we skip ideltime
            # checking because we assume the user has a process running, which
            # inevitably tampers with the idle time.
            user_processes = []
            for process in psutil.process_iter():
                try:
                    if process.username() == user:
                        user_processes.append(process.name())
                except (psutil.NoSuchProcess,
                        psutil.ZombieProcess,
                        psutil.AccessDenied):
                    # ignore processes which have disappeared etc.
                    pass

            skip = False
            for process in user_processes:
                if self._ignore_process_re.match(process) is not None:
                    self.logger.debug(
                        "Process %s with pid %s matches the ignore regex '%s'."
                        " Skipping idle time check for this user.",
                        process.name(), process.pid, self._ignore_process_re)
                    skip = True
                    break
            if skip:
                continue

            # prepare the environment for the xprintidle call
            env = copy.deepcopy(os.environ)
            env['DISPLAY'] = ':{}'.format(number)

            try:
                idle_time = subprocess.check_output(
                    ['sudo', '-u', user, 'xprintidle'], env=env)
                idle_time = float(idle_time.strip()) / 1000.0
            except (subprocess.CalledProcessError, ValueError) as error:
                self.logger.warning(
                    'Unable to determine the idle time for display %s.',
                    number, exc_info=True)
                raise TemporaryCheckError(error)

            self.logger.debug(
                'Idle time for display %s of user %s is %s seconds.',
                number, user, idle_time)

            if idle_time < self._timeout:
                return 'X session {} of user {} ' \
                    'has idle time {} < threshold {}'.format(
                        number, user, idle_time, self._timeout)

        return None


def execute_suspend(command):
    _logger.info('Suspending using command: %s', command)
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError:
        _logger.warning('Unable to execute suspend command: %s', command,
                        exc_info=True)


# pylint: disable=invalid-name
_checks = []
# pylint: enable=invalid-name

JUST_WOKE_UP_FILE = '/tmp/autosuspend-just-woke-up'


def loop(interval, idle_time, sleep_fn, all_checks=False):
    logger = logging.getLogger('loop')

    idle_since = None
    while True:
        logger.info('Starting new check iteration')

        matched = False
        for check in _checks:
            logger.debug('Executing check %s', check.name)
            try:
                result = check.check()
                if result is not None:
                    logger.info('Check %s matched. Reason: %s',
                                check.name,
                                result)
                    matched = True
                    if not all_checks:
                        logger.debug('Skipping further checks')
                        break
            except TemporaryCheckError:
                logger.warning('Check %s failed. Ignoring...', check,
                               exc_info=True)

        logger.debug('All checks have been executed')

        if os.path.isfile(JUST_WOKE_UP_FILE):
            logger.info('Just woke up from suspension. Resetting')
            os.remove(JUST_WOKE_UP_FILE)
            idle_since = None
            time.sleep(interval)
        elif matched:
            logger.info('Check iteration finished. System is active. '
                        'Sleeping until next iteration')
            idle_since = None
            time.sleep(interval)
        else:
            if idle_since is None:
                idle_since = time.time()
            logger.info('No checks matched. System is idle since %s',
                        idle_since)
            if time.time() - idle_since > idle_time:
                logger.info('System is idle long enough. Suspending...')
                sleep_fn()
                idle_since = None
            else:
                logger.info('Desired idle time of %s secs not reached so far. '
                            'Continuing checks', idle_time)
                time.sleep(interval)


def set_up_checks(config):

    check_section = [s for s in config.sections() if s.startswith('check.')]
    for section in check_section:
        name = section[len('check.'):]
        # legacy method to determine the check name from the section header
        class_name = name
        # if there is an explicit class, use that one with higher priority
        if 'class' in config[section]:
            class_name = config[section]['class']
        enabled = config.getboolean(section, 'enabled', fallback=False)

        if not enabled:
            _logger.debug('Skipping disabled check %s', name)
            continue

        _logger.info('Configuring check %s with class %s', name, class_name)
        try:
            klass = globals()[class_name]
        except KeyError:
            _logger.error('Cannot create check named %s: Class does not exist',
                          class_name)
            sys.exit(2)

        check = klass.create(name, config[section])
        if not isinstance(check, Check):
            _logger.exception('Check %s is not a correct Check instance',
                              check)
            sys.exit(2)
        _logger.debug('Created check instance %s', check)
        _checks.append(check)

    if not _checks:
        _logger.error('No checks enabled')
        sys.exit(2)


def parse_config(config_file):
    _logger.debug('Reading config file %s', config_file)
    config = configparser.ConfigParser()
    config.read_file(config_file)
    _logger.debug('Parsed config file: %s', config)
    return config


def parser_arguments():
    parser = argparse.ArgumentParser(
        description='Automatically suspends a server '
                    'based on several criteria',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    try:
        default_config = open('/etc/autosuspend.conf', 'r')
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        default_config = None
    parser.add_argument(
        '-c', '--config',
        dest='config_file',
        type=argparse.FileType('r'),
        default=default_config,
        required=default_config is None,
        metavar='FILE',
        help='The config file to use')
    parser.add_argument(
        '-a', '--allchecks',
        dest='all_checks',
        default=False,
        action='store_true',
        help='Execute all checks even if one has already prevented '
             'the system from going to sleep. Useful to debug individual '
             'checks.')
    parser.add_argument(
        '-l', '--logging',
        type=argparse.FileType('r'),
        nargs='?',
        default=False,
        const=True,
        metavar='FILE',
        help='Configures the python logging system. If used '
             'without an argument, all logging is enabled to '
             'the console. If used with an argument, the '
             'configuration is read from the specified file.')

    args = parser.parse_args()

    _logger.debug('Parsed command line arguments %s', args)

    return args


def configure_logging(file_or_flag):
    """
    Configure the python :mod:`logging` system.

    If the provided argument is a `file` instance, try to use the
    pointed to file as a configuration for the logging system. Otherwise,
    if the given argument evaluates to :class:True:, use a default
    configuration with many logging messages. If everything fails, just log
    starting from the warning level.

    Args:
        file_or_flag (file or bool):
            either a configuration file pointed by a :ref:`file object
            <python:bltin-file-objects>` instance or something that evaluates
            to :class:`bool`.
    """
    if isinstance(file_or_flag, bool):
        if file_or_flag:
            logging.basicConfig(level=logging.DEBUG)
        else:
            # at least configure warnings
            logging.basicConfig(level=logging.WARNING)
    else:
        try:
            logging.config.fileConfig(file_or_flag)
        except Exception as error:
            # at least configure warnings
            logging.basicConfig(level=logging.WARNING)
            _logger.warning('Unable to configure logging from file %s. '
                            'Falling back to warning level.',
                            file_or_flag,
                            exc_info=True)


def main():
    args = parser_arguments()
    configure_logging(args.logging)
    config = parse_config(args.config_file)
    set_up_checks(config)
    loop(config.getfloat('general', 'interval', fallback=60),
         config.getfloat('general', 'idle_time', fallback=300),
         functools.partial(execute_suspend,
                           config.get('general', 'suspend_cmd')),
         all_checks=args.all_checks)


if __name__ == "__main__":
    main()
