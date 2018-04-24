import os
import os.path

import pytest

import autosuspend


ROOT = os.path.dirname(os.path.realpath(__file__))

SUSPENSION_FILE = 'would_suspend'
WOKE_UP_FILE = 'test-woke-up'


@pytest.fixture
def suspension_file():
    try:
        os.remove(SUSPENSION_FILE)
    except OSError as error:
        pass

    class SuspensionFileFixture(object):

        def exists(self):
            return os.path.exists(SUSPENSION_FILE)

    yield SuspensionFileFixture()

    try:
        os.remove(SUSPENSION_FILE)
    except OSError as error:
        pass


def test_no_suspend_if_matching(suspension_file):
    autosuspend.main([
        '-c',
        os.path.join(ROOT, 'test_data', 'dont_suspend.conf'),
        '-r',
        '10',
        '-l'])

    assert not suspension_file.exists()


def test_suspend(suspension_file):
    autosuspend.main([
        '-c',
        os.path.join(ROOT, 'test_data', 'would_suspend.conf'),
        '-r',
        '10',
        '-l'])

    assert suspension_file.exists()


def test_woke_up_file_removed():
    try:
        open(WOKE_UP_FILE, 'a').close()
        autosuspend.main([
            '-c',
            os.path.join(ROOT, 'test_data', 'dont_suspend.conf'),
            '-r',
            '5',
            '-l'])
        assert not os.path.exists(WOKE_UP_FILE)
    finally:
        try:
            os.remove(WOKE_UP_FILE)
        except OSError as error:
            pass
