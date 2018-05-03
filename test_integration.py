import datetime
import os
import os.path

import autosuspend


ROOT = os.path.dirname(os.path.realpath(__file__))

SUSPENSION_FILE = 'would_suspend'
SCHEDULED_FILE = 'wakeup_at'
WOKE_UP_FILE = 'test-woke-up'
NOTIFY_FILE = 'notify'


def configure_config(config, tmpdir):
    out_path = tmpdir.join(config)
    with open(os.path.join(ROOT, 'test_data', config), 'r') as in_config:
        with out_path.open('w') as out_config:
            out_config.write(in_config.read().replace('@TMPDIR@',
                                                      tmpdir.strpath))
    return out_path


def test_no_suspend_if_matching(tmpdir):
    autosuspend.main([
        '-c',
        configure_config('dont_suspend.conf', tmpdir).strpath,
        '-r',
        '10',
        '-l'])

    assert not tmpdir.join(SUSPENSION_FILE).check()


def test_suspend(tmpdir):
    autosuspend.main([
        '-c',
        configure_config('would_suspend.conf', tmpdir).strpath,
        '-r',
        '10',
        '-l'])

    assert tmpdir.join(SUSPENSION_FILE).check()


def test_wakeup_scheduled(tmpdir):
    # configure when to wake up
    now = datetime.datetime.now(datetime.timezone.utc)
    wakeup_at = now + datetime.timedelta(hours=4)
    with tmpdir.join('wakeup_time').open('w') as out:
        out.write(str(wakeup_at.timestamp()))

    autosuspend.main([
        '-c',
        configure_config('would_schedule.conf', tmpdir).strpath,
        '-r',
        '10',
        '-l'])

    assert tmpdir.join(SUSPENSION_FILE).check()
    assert tmpdir.join(SCHEDULED_FILE).check()
    assert int(tmpdir.join(SCHEDULED_FILE).read()) == int(
        round((wakeup_at - datetime.timedelta(seconds=30)).timestamp()))


def test_woke_up_file_removed(tmpdir):
    tmpdir.join(WOKE_UP_FILE).ensure()
    autosuspend.main([
        '-c',
        configure_config('dont_suspend.conf', tmpdir).strpath,
        '-r',
        '5',
        '-l'])
    assert not tmpdir.join(WOKE_UP_FILE).check()


def test_notify_call(tmpdir):
    autosuspend.main([
        '-c',
        configure_config('notify.conf', tmpdir).strpath,
        '-r',
        '10',
        '-l'])

    assert tmpdir.join(SUSPENSION_FILE).check()
    assert tmpdir.join(NOTIFY_FILE).check()
    assert len(tmpdir.join(NOTIFY_FILE).read()) == 0


def test_notify_call_wakeup(tmpdir):
    # configure when to wake up
    now = datetime.datetime.now(datetime.timezone.utc)
    wakeup_at = now + datetime.timedelta(hours=4)
    with tmpdir.join('wakeup_time').open('w') as out:
        out.write(str(wakeup_at.timestamp()))

    autosuspend.main([
        '-c',
        configure_config('notify_wakeup.conf', tmpdir).strpath,
        '-r',
        '10',
        '-l'])

    assert tmpdir.join(SUSPENSION_FILE).check()
    assert tmpdir.join(NOTIFY_FILE).check()
    assert int(tmpdir.join(NOTIFY_FILE).read()) == int(
        round((wakeup_at - datetime.timedelta(seconds=10)).timestamp()))
