from setuptools import setup

setup(
    name='autosuspend',
    version='0.1',
    description='Automatically suspends a Linux server in case of no activity',
    author='Johannes Wienke',
    author_email='languitar@semipol.de',

    zip_safe=False,

    install_requires=[
        'psutil'
    ],

    scripts=[
        'autosuspend.py'
    ],
    data_files=[
        ('etc', ['autosuspend.conf', 'autosuspend-logging.conf'])
    ]
)
