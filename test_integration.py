import os
import os.path

import autosuspend


ROOT = os.path.dirname(os.path.realpath(__file__))

SUSPENSION_FILE = 'would_suspend'
WOKE_UP_FILE = 'test-woke-up'


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



def test_suspend(suspension_file):
    autosuspend.main([
        '-c',
        os.path.join(ROOT, 'test_data', 'would_suspend.conf'),
        '-r',
        '10',
        '-l'])

    assert suspension_file.exists()


def test_woke_up_file_removed(tmpdir):
    tmpdir.join(WOKE_UP_FILE).ensure()
    autosuspend.main([
        '-c',
        configure_config('dont_suspend.conf', tmpdir).strpath,
        '-r',
        '5',
        '-l'])
    assert not tmpdir.join(WOKE_UP_FILE).check()
