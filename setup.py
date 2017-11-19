from setuptools import setup

name='autosuspend'
version='0.7'
release='0.7-dev'

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
    },
    tests_require=[
        'pytest',
        'pytest-cov',
        'pytest-mock',
    ],

    scripts=[
        'autosuspend'
    ],
    data_files=[
        ('etc', ['autosuspend.conf',
                 'autosuspend-logging.conf']),
        ('lib/systemd/system', ['autosuspend.service',
                                'autosuspend-detect-suspend.service'])
    ],

    command_options={
        'build_sphinx': {
            'project': ('setup.py', name),
            'version': ('setup.py', version),
            'release': ('setup.py', release)
        }
    },
)
