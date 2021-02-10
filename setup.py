from pathlib import Path

from setuptools import find_packages, setup


name = "autosuspend"

version_file = (Path(__file__).absolute().parent / "VERSION")
lines = version_file.read_text().splitlines()
release = lines[1].strip()

extras_require = {
    "Mpd": ["python-mpd2"],
    "Kodi": ["requests"],
    "XPath": ["lxml", "requests"],
    "JSONPath": ["jsonpath-ng", "requests"],
    "Logind": ["dbus-python"],
    "ical": ["requests", "icalendar", "python-dateutil", "tzlocal"],
    "localfiles": ["requests-file"],
    "logactivity": ["python-dateutil", "pytz"],
    "test": [
        "pytest",
        "pytest-cov",
        "pytest-mock",
        "freezegun",
        "python-dbusmock",
        "PyGObject",
        "pytest-datadir",
        "pytest-httpserver",
    ],
}
extras_require["test"].extend(
    {dep for k, v in extras_require.items() if k != "test" for dep in v},
)

setup(
    name=name,
    version=release,
    description="A daemon to suspend your server in case of inactivity",
    author="Johannes Wienke",
    author_email="languitar@semipol.de",
    license="GPL2",
    zip_safe=False,
    python_requires=">=3.7",
    install_requires=[
        "psutil>=5.0",
        "portalocker",
    ],
    extras_require=extras_require,
    package_dir={
        "": "src",
    },
    packages=find_packages("src"),
    entry_points={
        "console_scripts": [
            "autosuspend = autosuspend:main",
        ],
    },
    data_files=[
        ("etc", ["data/autosuspend.conf", "data/autosuspend-logging.conf"]),
        (
            "lib/systemd/system",
            ["data/autosuspend.service", "data/autosuspend-detect-suspend.service"],
        ),
    ],
)
