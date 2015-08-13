#!/usr/bin/env python3

import abc
import argparse
import configparser
import functools
import logging
import os
import psutil
import re
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
            bool:
                ``True`` in case the check matches and the computer must NOT be
                suspended.

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
                return True
        return False


class Users(Check):

    @classmethod
    def create(cls, config, section):
        try:
            user_regex = re.compile(
                config.get(section, 'users', fallback='.*'))
            return cls(user_regex)
        except re.error as error:
            raise ConfigurationError(
                'SSH users regular expression is invalid: {}'.format(error))

    def __init__(self, user_regex):
        Check.__init__(self)
        self._user_regex = user_regex

    def check(self):
        for user, _, _, _ in psutil.users():
            if self._user_regex.fullmatch(user) is not None:
                self.logger.debug('User %s matches regex.', user)
                return True
        return False


class Smb(Check):

    @classmethod
    def create(cls, config, section):
        return cls()

    def check(self):
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
            sys.exit(2)
            return False
        elif smboutput_startline < len(smboutput_split):
            self.logger.debug(smboutput_startline)
            self.logger.debug("smb connection detected")
        self.logger.debug(smboutput_startline)
        return False


class Nfs(Check):

    @classmethod
    def create(cls, config, section):
        return cls()

    def check(self):
        nfscommand = "showmount --no-headers -a"
        nfsoutput = subprocess.getoutput(nfscommand + "| sed '/^$/d'")
        self.logger.debug("showmount:\n"+nfsoutput)
        nfsoutput_split = nfsoutput.splitlines()
        if len(nfsoutput_split) > 0:
            return True
        return False


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
                        self.logger.debug(pinfo + " " + name)
                        return True
            except psutil.NoSuchProcess:
                pass
        return False


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
        return loadcurrent > self._threshold


# Execute suspend
def execute_suspend(command):
    _logger.info('Suspending using command: %s', command)
    try:
        os.system(command)
    except:
        _logger.warning('Unable to execute suspend command: %s', command,
                        exc_info=True)


# pylint: disable=invalid-name
_checks = []
# pylint: enable=invalid-name


def loop(interval, idle_time, sleep_fn):
    logger = logging.getLogger('loop')

    idle_since = None
    while True:
        logger.info('Starting new check iteration')

        matched = False
        for check in _checks:
            logger.debug('Executing check %s', check)
            try:
                matched = check.check()
                if matched:
                    logger.info('Check %s matched. '
                                'Skipping further checks and suspend',
                                check)
                    break
            except TemporaryCheckError:
                logger.warning('Check %s failed. Ignoring...', check,
                               exc_info=True)

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
    _logger.debug('Reading config file %s')
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

    args = parser.parse_args()

    _logger.debug('Parsed command line arguments %s', args)

    return args


def main():
    logging.basicConfig(level=logging.DEBUG)
    args = parser_arguments()
    config = parse_config(args.config_file)
    set_up_checks(config)
    loop(config.getfloat('general', 'interval', fallback=60),
         config.getfloat('general', 'idle_time', fallback=300),
         functools.partial(execute_suspend,
                           config.get('general', 'suspend_cmd')))


if __name__ == "__main__":
    main()
