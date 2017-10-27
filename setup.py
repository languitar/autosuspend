from setuptools import setup

setup(
    name='autosuspend',
    version='0.5.1',

    description='A daemon to suspend your server in case of inactivity',
    author='Johannes Wienke',
    author_email='languitar@semipol.de',
    license='GPL2',

    zip_safe=False,

    setup_requires=[
        'pytest-runner',
    ],
    install_requires=[
        'psutil',
    ],
    extras_require={
        'Mpd': ['python-mpd2']
    },
    tests_require=[
        'pytest',
        'pytest-cov',
        'pytest-mock',
    ],

    scripts=[
        'autosuspend.py'
    ],
    data_files=[
        ('etc', ['autosuspend.conf',
                 'autosuspend-logging.conf']),
        ('lib/systemd/system', ['autosuspend.service',
                                'autosuspend-detect-suspend.service'])
    ]
)
