#!/usr/bin/env python3

import abc
import argparse
import configparser
import functools
import logging
import logging.config
import os
import psutil
import re
import socket
import subprocess
import sys
import time


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
    def create(cls, config, section):
        """
        Factory method to create an appropriate instance of the check for the
        provided options.

        Args:
            config (configparser.ConfigParser):
                parser object containing the configuration options to use
            section (str):
                name of the section in the config parser the appropriate
                options are contained in

        Raises:
            ConfigurationError:
                Configuration for this check is inappropriate
        """
        pass

    def __init__(self):
        self.logger = logging.getLogger(
            'check.{}'.format(self.__class__.__name__))

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


class Ping(Check):

    @classmethod
    def create(cls, config, section):
        try:
            hosts = config.get(section, 'hosts').split(',')
            hosts = [h.strip() for h in hosts]
            return cls(hosts)
        except configparser.NoOptionError as error:
            raise ConfigurationError(
                'Unable to determine hosts to ping: {}'.format(error))

    def __init__(self, hosts):
        Check.__init__(self)
        self._hosts = hosts

    def check(self):
        # TODO reimplement this
        for host in self._hosts:
            pingcmd = "ping -q -c 1 " + host + " &> /dev/null"
            if os.system(pingcmd) == 0:
                self.logger.debug("host " + host + " appears to be up")
                return 'Host {} is up'.format(host)
        return None


class Mpd(Check):

    @classmethod
    def create(cls, config, section):
        try:
            host = config.get(section, 'host', fallback='localhost')
            port = config.getint(section, 'port', fallback=6600)
            timeout = config.getint(section, 'timeout', fallback=6600)
            return cls(host, port, timeout)
        except configparser.NoOptionError as error:
            raise ConfigurationError(
                'Host port configuration wrong: {}'.format(error))

    def __init__(self, host, port, timeout):
        Check.__init__(self)
        self._host = host
        self._port = port
        self._timeout = timeout

    def check(self):
        from mpd import MPDClient
        try:
            client = MPDClient()
            client.timeout = self._timeout
            client.connect(self._host, self._port)
            state = client.status()
            client.close()
            client.disconnect()
            if state['state'] == 'play':
                return 'MPD currently playing'
            else:
                return None
        except (ConnectionError,
                ConnectionRefusedError,
                socket.gaierror) as error:
            raise TemporaryCheckError(error)


class Users(Check):

    @classmethod
    def create(cls, config, section):
        try:
            user_regex = re.compile(
                config.get(section, 'name', fallback='.*'))
            terminal_regex = re.compile(
                config.get(section, 'terminal', fallback='.*'))
            host_regex = re.compile(
                config.get(section, 'host', fallback='.*'))
            return cls(user_regex, terminal_regex, host_regex)
        except re.error as error:
            raise ConfigurationError(
                'Users regular expression is invalid: {}'.format(error))

    def __init__(self, user_regex, terminal_regex, host_regex):
        Check.__init__(self)
        self._user_regex = user_regex
        self._terminal_regex = terminal_regex
        self._host_regex = host_regex

    def check(self):
        for user, terminal, host, started in psutil.users():
            if self._user_regex.fullmatch(user) is not None and \
                    self._terminal_regex.fullmatch(terminal) is not None and \
                    self._host_regex.fullmatch(host) is not None:
                self.logger.debug('User %s on terminal %s from host %s '
                                  'matches criteria.', user, terminal, host)
                return 'User {user} is logged in on terminal {terminal} ' \
                    'from {host} since {started}'.format(user=user,
                                                         terminal=terminal,
                                                         host=host,
                                                         started=started)
        return None


class Smb(Check):

    @classmethod
    def create(cls, config, section):
        return cls()

    def check(self):
        # TODO fix this
        smbcommand = "smbstatus -b"
        smboutput = subprocess.getoutput(smbcommand + "| sed '/^$/d'")
        self.logger.debug("smboutput:\n"+smboutput)
        smboutput_split = smboutput.splitlines()
        smboutput_startline = -1
        self.logger.debug(len(smboutput_split))
        for line in range(len(smboutput_split)):
            if smboutput_split[line].startswith("----"):
                smboutput_startline = line+1

        if smboutput_startline == -1:
            self.logger.debug(smboutput)
            self.logger.info(
                'Execution of smbstatus failed or '
                'generated unexpected output.')
            raise SevereCheckError()
        elif smboutput_startline < len(smboutput_split):
            self.logger.debug(smboutput_startline)
            self.logger.debug("smb connection detected")
        self.logger.debug(smboutput_startline)
        return None


class Nfs(Check):

    @classmethod
    def create(cls, config, section):
        return cls()

    def check(self):
        # TODO fix this
        nfscommand = "showmount --no-headers -a"
        nfsoutput = subprocess.getoutput(nfscommand + "| sed '/^$/d'")
        self.logger.debug("showmount:\n"+nfsoutput)
        nfsoutput_split = nfsoutput.splitlines()
        if len(nfsoutput_split) > 0:
            return 'NFS connection open'
        return None


class Processes(Check):

    @classmethod
    def create(cls, config, section):
        try:
            processes = config.get(section, 'processes').split(',')
            processes = [p.strip() for p in processes]
            return cls(processes)
        except configparser.NoOptionError:
            raise ConfigurationError('No processes to check specified')

    def __init__(self, processes):
        Check.__init__(self)
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
    def create(cls, config, section):
        try:
            ports = config.get(section, 'ports')
            ports = ports.split(',')
            ports = [p.strip() for p in ports]
            ports = set([int(p) for p in ports])
            return cls(ports)
        except configparser.NoOptionError:
            raise ConfigurationError('Missing option ports')
        except ValueError:
            raise ConfigurationError('Ports must be integers')

    def __init__(self, ports):
        Check.__init__(self)
        self._ports = ports

    def check(self):
        try:
            out = subprocess.check_output(['ss', '-n'],
                                          universal_newlines=True)
            lines = out.split('\n')
            lines = lines[1:]
            lines = [l for l in lines if l.startswith('tcp')]
            lines = [l for l in lines if 'ESTAB' in l]
            open_ports = [l.split()[4].split(':')[-1] for l in lines]
            open_ports = set([int(p) for p in open_ports])
            self.logger.debug('Matching open ports: %s',
                              self._ports.intersection(open_ports))
            intersection = open_ports.intersection(self._ports)
            if intersection:
                return 'Ports {} are connected'.format(intersection)
        except subprocess.CalledProcessError:
            self.logger.error('Unable to call ss utility', exc_info=True)
            raise SevereCheckError()


class Load(Check):

    @classmethod
    def create(cls, config, section):
        try:
            return cls(config.getfloat(section, 'threshold', fallback=2.5))
        except ValueError as error:
            raise ConfigurationError(
                'Unable to parse threshold as float: {}'.format(error))

    def __init__(self, threshold):
        Check.__init__(self)
        self._threshold = threshold

    def check(self):
        loadcurrent = os.getloadavg()[1]
        self.logger.debug("Load: %s", loadcurrent)
        if loadcurrent > self._threshold:
            return 'Load {} > threshold {}'.format(loadcurrent,
                                                   self._threshold)
        else:
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


def loop(interval, idle_time, sleep_fn, all_checks=False):
    logger = logging.getLogger('loop')

    idle_since = None
    while True:
        logger.info('Starting new check iteration')

        matched = False
        for check in _checks:
            logger.debug('Executing check %s', check.__class__.__name__)
            try:
                result = check.check()
                if result is not None:
                    logger.info('Check %s matched. Reason: %s',
                                check.__class__.__name__,
                                result)
                    matched = True
                    if not all_checks:
                        logger.debug('Skipping further checks')
                        break
            except TemporaryCheckError:
                logger.warning('Check %s failed. Ignoring...', check,
                               exc_info=True)

        logger.debug('All checks have been executed')

        if matched:
            logger.info('Check iteration finished. '
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
        class_name = section[len('check.'):]
        enabled = config.getboolean(section, 'enabled', fallback=False)

        if not enabled:
            _logger.debug('Skipping disabled check %s', class_name)
            continue

        _logger.info('Configuring check %s', class_name)
        try:
            klass = globals()[class_name]
        except KeyError:
            _logger.error('Cannot create check named %s: Class does not exist',
                          class_name)
            sys.exit(2)

        check = klass.create(config, section)
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
