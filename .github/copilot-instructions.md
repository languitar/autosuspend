# Copilot Instructions for autosuspend

## Project Overview

`autosuspend` is a Python daemon that suspends a system when certain conditions are met or not met. It monitors system activity and scheduled events without requiring X infrastructure, making it ideal for headless servers.

## Build, Test, and Lint Commands

The project uses `tox` to manage all testing and checking workflows.

### Running Tests

```bash
# Run all unit tests (excludes integration tests)
tox -e test

# Run specific test file or test
tox -e test -- tests/test_checks.py
tox -e test -- tests/test_checks.py::TestCheckName

# Run integration tests
tox -e integration

# Run tests with minimal dependencies
tox -e mindeps

# Generate coverage report
tox -e coverage
```

### Linting and Type Checking

```bash
# Run all checks (ruff, isort, black, mypy)
tox -e check

# Individual linters
ruff check src tests
isort --check src tests
black --check src tests
mypy src tests
```

### Documentation

```bash
# Build Sphinx documentation
tox -e docs
```

### Python Versions

The project supports Python 3.11+. Tests run against Python 3.11, 3.12, 3.13, and 3.14.

## Architecture

### Check System

The core architecture revolves around a plugin-based check system with two main check types:

1. **Activity Checks** (`Activity` subclasses): Determine if the system should NOT be suspended
   - Located in `src/autosuspend/checks/activity.py` and module files
   - Return `True` if activity is detected (blocks suspend), `False` otherwise
   - Examples: `Ping`, `Users`, `ActiveConnection`, `Load`, `Smb`, `Kodi`

2. **Wakeup Checks** (`Wakeup` subclasses): Determine when the system should wake up
   - Located in `src/autosuspend/checks/wakeup.py` and module files
   - Return a `datetime` object for the next scheduled wakeup, or `None`
   - Examples: `Calendar`, `File`, `Command`, `Periodic`

### Check Implementation Pattern

All checks:
- Inherit from `Check` base class (and either `Activity` or `Wakeup`)
- Must implement a `create()` classmethod that parses configuration
- Must implement the check logic method (`check()` or `check_wakeup()`)
- Use the `@logger_by_class_instance` pattern for logging
- Handle errors by raising `TemporaryCheckError` (recoverable) or `SevereCheckError` (fatal)

### Optional Dependencies

The project uses extras to manage optional check dependencies:
- `Mpd`: python-mpd2
- `Kodi`: requests
- `XPath`: lxml, requests
- `JSONPath`: jsonpath-ng, requests
- `Logind`: dbus-python
- `ical`: requests, icalendar, python-dateutil, tzlocal
- `localfiles`: requests-file
- `logactivity`: python-dateutil, tzdata

Check modules use `contextlib.suppress(ModuleNotFoundError)` to gracefully handle missing optional dependencies.

### Main Daemon Loop

The daemon (in `src/autosuspend/__init__.py`):
1. Reads configuration from `/etc/autosuspend.conf`
2. Instantiates enabled checks
3. Runs activity checks in a loop at configured intervals
4. If all activity checks return `False` for `idle_time` seconds, runs wakeup checks
5. Executes the suspend command with optional notification
6. Can schedule wake-up using RTC alarms

## Key Conventions

### Configuration File Format

Uses INI format with specific section prefixes:
- `[general]`: Main daemon configuration
- `[check.{Name}]`: Activity check configuration
- `[wakeup.{Name}]`: Wakeup check configuration
- Checks can use `class = ClassName` to specify the check class if section name differs
- All checks are `enabled = false` by default and must be explicitly enabled

### Testing Patterns

- Test files mirror source structure: `test_checks_*.py` for check modules
- Use `pytest` with markers: `@pytest.mark.integration` for integration tests
- Use `pytest-mock` for mocking, `freezegun` for time manipulation
- Use `pytest-datadir` for test data files
- Tests for checks with external dependencies use `pytest-httpserver` and `python-dbusmock`

### Code Style

- Follows Ruff linting rules with Google-style docstrings (`pydocstyle.convention = "google"`)
- Uses Black for formatting, isort for import sorting
- Type hints required (`mypy --disallow-untyped-defs`)
- Imports are sorted with isort profile "black"
- Shell commands in checks are acceptable (explicitly allowed via `S602`, `S603`, `S607`)

### Module Organization

- Core check infrastructure in `src/autosuspend/checks/__init__.py`
- Individual check implementations in separate modules by category (e.g., `linux.py`, `kodi.py`, `systemd.py`)
- Utility mixins in `src/autosuspend/checks/util.py` (e.g., `NetworkMixin`, `CommandMixin`)
- Test utilities in `tests/utils.py`

### Logging

- Use `logger_by_class_instance` decorator for check classes
- Logger names follow pattern `autosuspend.checks.{module}.{classname}`
- Configuration file supports Python's `logging.config` format

### Release Process

The project uses semantic-release for automated releases:
- Conventional commits are enforced via commitlint
- Releases trigger automatically on main branch pushes
- Version is stored in `VERSION` file
