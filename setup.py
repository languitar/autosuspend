import os
import os.path

from setuptools import find_packages, setup

name = 'autosuspend'

with open(os.path.join(
        os.path.abspath(os.path.dirname(os.path.realpath(__file__))),
        'VERSION'), 'r') as version_file:
    lines = version_file.readlines()
release = lines[1].strip()

setup(
    name=name,
    version=release,

    description='A daemon to suspend your server in case of inactivity',
    author='Johannes Wienke',
    author_email='languitar@semipol.de',
    license='GPL2',

    zip_safe=False,

    setup_requires=[
        'pytest-runner',
    ],
    install_requires=[
        'psutil>=5.0',
    ],
    extras_require={
        'Mpd': ['python-mpd2'],
        'Kodi': ['requests'],
        'XPath': ['lxml', 'requests'],
        'Logind': ['dbus-python'],
        'ical': ['requests', 'icalendar', 'python-dateutil', 'tzlocal'],
        'localfiles': ['requests-file'],
        'test': ['pytest', 'pytest-cov', 'pytest-mock', 'freezegun'],
    },

    package_dir={
        '': 'src',
    },
    packages=find_packages('src'),

    entry_points={
        'console_scripts': [
            'autosuspend = autosuspend:main',
        ],
    },

    data_files=[
        ('etc', ['data/autosuspend.conf',
                 'data/autosuspend-logging.conf']),
        ('lib/systemd/system', ['data/autosuspend.service',
                                'data/autosuspend-detect-suspend.service']),
    ],
)
