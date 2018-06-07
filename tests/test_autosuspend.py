import configparser
from datetime import datetime, timedelta, timezone
import logging
import subprocess

import pytest

import autosuspend


class TestExecuteSuspend(object):

    def test_smoke(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        command = ['foo', 'bar']
        autosuspend.execute_suspend(command, None)
        mock.assert_called_once_with(command, shell=True)

    def test_call_exception(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        command = ['foo', 'bar']
        mock.side_effect = subprocess.CalledProcessError(2, command)

        spy = mocker.spy(autosuspend._logger, 'warning')

        autosuspend.execute_suspend(command, None)

        mock.assert_called_once_with(command, shell=True)
        assert spy.call_count == 1


class TestScheduleWakeup(object):

    def test_smoke(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        dt = datetime.fromtimestamp(1525270801, timezone(timedelta(hours=4)))
        autosuspend.schedule_wakeup('echo {timestamp:.0f} {iso}', dt)
        mock.assert_called_once_with(
            'echo 1525270801 2018-05-02T18:20:01+04:00', shell=True)

    def test_call_exception(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        mock.side_effect = subprocess.CalledProcessError(2, "foo")

        spy = mocker.spy(autosuspend._logger, 'warning')

        autosuspend.schedule_wakeup("foo", datetime.now(timezone.utc))

        mock.assert_called_once_with("foo", shell=True)
        assert spy.call_count == 1


class TestConfigureLogging(object):

    def test_debug(self, mocker):
        mock = mocker.patch('logging.basicConfig')

        autosuspend.configure_logging(True)

        mock.assert_called_once_with(level=logging.DEBUG)

    def test_standard(self, mocker):
        mock = mocker.patch('logging.basicConfig')

        autosuspend.configure_logging(False)

        mock.assert_called_once_with(level=logging.WARNING)

    def test_file(self, mocker):
        mock = mocker.patch('logging.config.fileConfig')

        # anything that is not a boolean is treated like a file
        autosuspend.configure_logging(42)

        mock.assert_called_once_with(42)

    def test_file_fallback(self, mocker):
        mock = mocker.patch('logging.config.fileConfig',
                            side_effect=RuntimeError())
        mock_basic = mocker.patch('logging.basicConfig')

        # anything that is not a boolean is treated like a file
        autosuspend.configure_logging(42)

        mock.assert_called_once_with(42)
        mock_basic.assert_called_once_with(level=logging.WARNING)


class TestSetUpChecks(object):

    def test_smoke(self, mocker):
        mock_class = mocker.patch('autosuspend.checks.activity.Mpd')
        mock_class.create.return_value = mocker.MagicMock(
            spec=autosuspend.checks.Activity)

        parser = configparser.ConfigParser()
        parser.read_string('''[check.Foo]
                           class = Mpd
                           enabled = True''')

        autosuspend.set_up_checks(parser, 'check', 'activity',
                                  autosuspend.Activity)

        mock_class.create.assert_called_once_with('Foo', parser['check.Foo'])

    def test_external_class(self, mocker):
        mock_class = mocker.patch('os.path.TestCheck', create=True)
        mock_class.create.return_value = mocker.MagicMock(
            spec=autosuspend.checks.Activity)
        parser = configparser.ConfigParser()
        parser.read_string('''[check.Foo]
                           class = os.path.TestCheck
                           enabled = True''')

        autosuspend.set_up_checks(parser, 'check', 'activity',
                                  autosuspend.Activity)

        mock_class.create.assert_called_once_with('Foo', parser['check.Foo'])

    def test_not_enabled(self, mocker):
        mock_class = mocker.patch('autosuspend.checks.activity.Mpd')
        mock_class.create.return_value = mocker.MagicMock(
            spec=autosuspend.Activity)

        parser = configparser.ConfigParser()
        parser.read_string('''[check.Foo]
                           class = Mpd
                           enabled = False''')

        autosuspend.set_up_checks(parser, 'check', 'activity',
                                  autosuspend.Activity)

        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.set_up_checks(parser, 'check', 'activity',
                                      autosuspend.Activity,
                                      error_none=True)

    def test_no_such_class(self, mocker):
        parser = configparser.ConfigParser()
        parser.read_string('''[check.Foo]
                           class = FooBarr
                           enabled = True''')
        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.set_up_checks(parser, 'check', 'activity',
                                      autosuspend.Activity)

    def test_not_a_check(self, mocker):
        mock_class = mocker.patch('autosuspend.checks.activity.Mpd')
        mock_class.create.return_value = mocker.MagicMock()

        parser = configparser.ConfigParser()
        parser.read_string('''[check.Foo]
                           class = Mpd
                           enabled = True''')

        with pytest.raises(autosuspend.ConfigurationError):
            autosuspend.set_up_checks(parser, 'check', 'activity',
                                      autosuspend.Activity)

        mock_class.create.assert_called_once_with('Foo', parser['check.Foo'])


class TestExecuteChecks(object):

    def test_no_checks(self, mocker):
        assert autosuspend.execute_checks(
            [], False, mocker.MagicMock()) is False

    def test_matches(self, mocker):
        matching_check = mocker.MagicMock(
            spec=autosuspend.Activity)
        matching_check.name = 'foo'
        matching_check.check.return_value = "matches"
        assert autosuspend.execute_checks(
            [matching_check], False, mocker.MagicMock()) is True
        matching_check.check.assert_called_once_with()

    def test_only_first_called(self, mocker):
        matching_check = mocker.MagicMock(
            spec=autosuspend.Activity)
        matching_check.name = 'foo'
        matching_check.check.return_value = "matches"
        second_check = mocker.MagicMock()
        second_check.name = 'bar'
        second_check.check.return_value = "matches"

        assert autosuspend.execute_checks(
            [matching_check, second_check],
            False,
            mocker.MagicMock()) is True
        matching_check.check.assert_called_once_with()
        second_check.check.assert_not_called()

    def test_all_called(self, mocker):
        matching_check = mocker.MagicMock(
            spec=autosuspend.Activity)
        matching_check.name = 'foo'
        matching_check.check.return_value = "matches"
        second_check = mocker.MagicMock()
        second_check.name = 'bar'
        second_check.check.return_value = "matches"

        assert autosuspend.execute_checks(
            [matching_check, second_check],
            True,
            mocker.MagicMock()) is True
        matching_check.check.assert_called_once_with()
        second_check.check.assert_called_once_with()

    def test_ignore_temporary_errors(self, mocker):
        matching_check = mocker.MagicMock(
            spec=autosuspend.Activity)
        matching_check.name = 'foo'
        matching_check.check.side_effect = autosuspend.TemporaryCheckError()
        second_check = mocker.MagicMock()
        second_check.name = 'bar'
        second_check.check.return_value = "matches"

        assert autosuspend.execute_checks(
            [matching_check, second_check],
            False,
            mocker.MagicMock()) is True
        matching_check.check.assert_called_once_with()
        second_check.check.assert_called_once_with()


class TestExecuteWakeups(object):

    def test_no_wakeups(self, mocker):
        assert autosuspend.execute_wakeups(
            [], 0, mocker.MagicMock()) is None

    def test_all_none(self, mocker):
        wakeup = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup.check.return_value = None
        assert autosuspend.execute_wakeups(
            [wakeup], 0, mocker.MagicMock()) is None

    def test_basic_return(self, mocker):
        wakeup = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        now = datetime.now(timezone.utc)
        wakeup_time = now + timedelta(seconds=10)
        wakeup.check.return_value = wakeup_time
        assert autosuspend.execute_wakeups(
            [wakeup], now, mocker.MagicMock()) == wakeup_time

    def test_soonest_taken(self, mocker):
        reference = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup.check.return_value = reference + timedelta(seconds=20)
        earlier = reference + timedelta(seconds=10)
        wakeup_earlier = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup_earlier.check.return_value = earlier
        in_between = reference + timedelta(seconds=15)
        wakeup_later = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup_later.check.return_value = in_between
        assert autosuspend.execute_wakeups(
            [wakeup, wakeup_earlier, wakeup_later],
            reference, mocker.MagicMock()) == earlier

    def test_ignore_temporary_errors(self, mocker):
        now = datetime.now(timezone.utc)

        wakeup = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup.check.return_value = now + timedelta(seconds=20)
        wakeup_error = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup_error.check.side_effect = autosuspend.TemporaryCheckError()
        wakeup_earlier = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup_earlier.check.return_value = now + timedelta(seconds=10)
        assert autosuspend.execute_wakeups(
            [wakeup, wakeup_error, wakeup_earlier],
            now, mocker.MagicMock()) == now + timedelta(seconds=10)

    def test_ignore_too_early(self, mocker):
        now = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(
            spec=autosuspend.Wakeup)
        wakeup.check.return_value = now
        assert autosuspend.execute_wakeups(
            [wakeup], now, mocker.MagicMock()) is None
        assert autosuspend.execute_wakeups(
            [wakeup], now + timedelta(seconds=1), mocker.MagicMock()) is None


class TestNotifySuspend(object):

    def test_date(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        dt = datetime.fromtimestamp(1525270801, timezone(timedelta(hours=4)))
        autosuspend.notify_suspend(
            'echo {timestamp:.0f} {iso}', 'not this', dt)
        mock.assert_called_once_with(
            'echo 1525270801 2018-05-02T18:20:01+04:00', shell=True)

    def test_date_no_command(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        dt = datetime.fromtimestamp(1525270801, timezone(timedelta(hours=4)))
        autosuspend.notify_suspend(None, 'not this', dt)
        mock.assert_not_called()

    def test_no_date(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        autosuspend.notify_suspend(
            'echo {timestamp:.0f} {iso}', 'echo nothing', None)
        mock.assert_called_once_with('echo nothing', shell=True)

    def test_no_date_no_command(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        autosuspend.notify_suspend(
            'echo {timestamp:.0f} {iso}', None, None)
        mock.assert_not_called()

    def test_ignore_execution_errors(self, mocker):
        mock = mocker.patch('subprocess.check_call')
        mock.side_effect = subprocess.CalledProcessError(2, 'cmd')
        dt = datetime.fromtimestamp(1525270801, timezone(timedelta(hours=4)))
        autosuspend.notify_suspend(None, 'not this', dt)


def test_notify_and_suspend(mocker):
    mock = mocker.patch('subprocess.check_call')
    dt = datetime.fromtimestamp(1525270801, timezone(timedelta(hours=4)))
    autosuspend.notify_and_suspend('echo suspend',
                                   'echo notify {timestamp:.0f} {iso}',
                                   'not this',
                                   dt)
    mock.assert_has_calls([
        mocker.call('echo notify 1525270801 2018-05-02T18:20:01+04:00',
                    shell=True),
        mocker.call('echo suspend', shell=True)])


class _StubCheck(autosuspend.Activity):

    @classmethod
    def create(cls, name, config):
        pass

    def __init__(self, name, match):
        autosuspend.Activity.__init__(self, name)
        self.match = match

    def check(self):
        return self.match


@pytest.fixture
def sleep_fn():

    class Func(object):

        def __init__(self):
            self.called = False
            self.call_arg = None

        def reset(self):
            self.called = False
            self.call_arg = None

        def __call__(self, arg):
            self.called = True
            self.call_arg = arg

    return Func()


@pytest.fixture
def wakeup_fn():

    class Func(object):

        def __init__(self):
            self.call_arg = None

        def reset(self):
            self.call_arg = None

        def __call__(self, arg):
            self.call_arg = arg

    return Func()


class TestProcessor(object):

    def test_smoke(self, sleep_fn, wakeup_fn):
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [],
                                          2,
                                          0,
                                          0,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)
        # should init the timestamp initially
        start = datetime.now(timezone.utc)
        processor.iteration(start, False)
        assert not sleep_fn.called
        # not yet reached
        processor.iteration(start + timedelta(seconds=1), False)
        assert not sleep_fn.called
        # time must be greater, not equal
        processor.iteration(start + timedelta(seconds=2), False)
        assert not sleep_fn.called
        # go to sleep
        processor.iteration(start + timedelta(seconds=3), False)
        assert sleep_fn.called
        assert sleep_fn.call_arg is None

        sleep_fn.reset()

        # second iteration to check that the idle time got reset
        processor.iteration(start + timedelta(seconds=4), False)
        assert not sleep_fn.called
        # go to sleep again
        processor.iteration(start + timedelta(seconds=6, milliseconds=2),
                            False)
        assert sleep_fn.called

        assert wakeup_fn.call_arg is None

    def test_just_woke_up_handling(self, sleep_fn, wakeup_fn):
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [],
                                          2,
                                          0,
                                          0,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)

        # should init the timestamp initially
        start = datetime.now(timezone.utc)
        processor.iteration(start, False)
        assert not sleep_fn.called
        # should go to sleep but we just woke up
        processor.iteration(start + timedelta(seconds=3), True)
        assert not sleep_fn.called
        # start over again
        processor.iteration(start + timedelta(seconds=4), False)
        assert not sleep_fn.called
        # not yet sleeping
        processor.iteration(start + timedelta(seconds=6), False)
        assert not sleep_fn.called
        # now go to sleep
        processor.iteration(start + timedelta(seconds=7), False)
        assert sleep_fn.called

        assert wakeup_fn.call_arg is None

    def test_wakeup_blocks_sleep(self, mocker, sleep_fn, wakeup_fn):
        start = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(spec=autosuspend.Wakeup)
        wakeup.check.return_value = start + timedelta(seconds=6)
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [wakeup],
                                          2,
                                          10,
                                          0,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)

        # init iteration
        processor.iteration(start, False)
        # no activity and enough time passed to start sleeping
        processor.iteration(start + timedelta(seconds=3), False)
        assert not sleep_fn.called
        assert wakeup_fn.call_arg is None

    def test_wakeup_scheduled(self, mocker, sleep_fn, wakeup_fn):
        start = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(spec=autosuspend.Wakeup)
        wakeup.check.return_value = start + timedelta(seconds=25)
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [wakeup],
                                          2,
                                          10,
                                          0,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)

        # init iteration
        processor.iteration(start, False)
        # no activity and enough time passed to start sleeping
        processor.iteration(start + timedelta(seconds=3), False)
        assert sleep_fn.called
        assert sleep_fn.call_arg == start + timedelta(seconds=25)
        assert wakeup_fn.call_arg == start + timedelta(seconds=25)

        sleep_fn.reset()
        wakeup_fn.reset()

        # ensure that wake up is not scheduled again
        processor.iteration(start + timedelta(seconds=25), False)
        assert wakeup_fn.call_arg is None

    def test_wakeup_delta_blocks(self, mocker, sleep_fn, wakeup_fn):
        start = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(spec=autosuspend.Wakeup)
        wakeup.check.return_value = start + timedelta(seconds=25)
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [wakeup],
                                          2,
                                          10,
                                          22,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)

        # init iteration
        processor.iteration(start, False)
        # no activity and enough time passed to start sleeping
        processor.iteration(start + timedelta(seconds=3), False)
        assert not sleep_fn.called

    def test_wakeup_delta_applied(self, mocker, sleep_fn, wakeup_fn):
        start = datetime.now(timezone.utc)
        wakeup = mocker.MagicMock(spec=autosuspend.Wakeup)
        wakeup.check.return_value = start + timedelta(seconds=25)
        processor = autosuspend.Processor([_StubCheck('stub', None)],
                                          [wakeup],
                                          2,
                                          10,
                                          4,
                                          sleep_fn,
                                          wakeup_fn,
                                          False)

        # init iteration
        processor.iteration(start, False)
        # no activity and enough time passed to start sleeping
        processor.iteration(start + timedelta(seconds=3), False)
        assert sleep_fn.called
        assert wakeup_fn.call_arg == start + timedelta(seconds=21)
