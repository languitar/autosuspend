# AGENTS.md

## project overview

`autosuspend` is a Python daemon that suspends a system based on configured activity checks and wakeup conditions.
It enables servers to sleep on inactivity without depending on X infrastructure.
The project uses a pluggable check system where different activity monitors (like iCal events, MPD, Kodi, system logs, etc.) determine if the system should remain active.

## development commands

### environment setup

Install development dependencies:

```bash
pip install -e ".[test]"
```

### testing

Run all tests with tox (tests multiple Python versions and dependency combinations):

```bash
tox
```

Run tests for a specific Python version:

```bash
tox -e test-py311
```

Run a single test:

```bash
pytest tests/test_checks_ical.py::TestActiveCalendarEvent::test_smoke
```

Run tests excluding integration tests (faster):

```bash
pytest -m "not integration"
```

Run tests with coverage report:

```bash
pytest --cov
```

### Code quality

Lint code with ruff:

```bash
ruff check src tests
```

Format with black and isort:

```bash
black src tests
isort src tests
```

Type check with mypy:

```bash
mypy src tests
```

Run all checks (same as CI):

```bash
tox -e check
```

### Documentation

Build Sphinx documentation:

```bash
tox -e docs
```

### Test minimal dependencies

Verify the project works without optional dependencies:

```bash
tox -e mindeps
```

## Architecture

### Core components

- Checks System (`src/autosuspend/checks/`): Pluggable check modules that determine if system should suspend
  - Activity checks (inherit from `Activity`): Monitor specific activity sources and return a string if activity is detected, `None` if safe to suspend
  - Wakeup checks (inherit from `Wakeup`): Determine when the system should wake up (e.g., calendar events)
  - Base classes provide configuration schema support and logging

- Main Daemon (`src/autosuspend/__init__.py`): Coordinates check execution, handles D-Bus suspension, manages inhibit locks

- Configuration (`src/autosuspend/config.py`): Parses configuration file and validates check parameters

- Utilities (`src/autosuspend/util/`): D-Bus interactions, datetime utilities, logging helpers

### Check modules

- `activity.py`: Basic CPU/load monitoring
- `command.py`: Execute shell commands and check output
- `ical.py`: iCalendar events (requires `requests`, `icalendar`, `python-dateutil`, `tzlocal`)
- `json.py`: JSON API responses
- `kodi.py`: Kodi media center activity
- `linux.py`: Linux-specific checks (system load, memory)
- `logs.py`: Log file activity monitoring
- `mpd.py`: Music Player Daemon activity
- `smb.py`: Samba/SMB activity
- `systemd.py`: systemd-logind inhibit locks
- `wakeup.py`: Abstract base for wakeup checks
- `xorg.py`: X11 activity monitoring
- `xpath.py`: XPath-based HTTP API monitoring
- `stub.py`: Stub implementations for testing

## Testing strategy

### Test structure

- Tests use pytest with freezegun for time mocking
- Test data files in `tests/test_checks_*/` subdirectories (one per module)
- Fixtures in `tests/conftest.py` including `serve_file` for HTTP testing
- Coverage target: ~90%

### Test data notes

Test data files (especially iCal files) contain hardcoded dates.
When events expire relative to current date, tests will fail.
Example: `long-event.ics` has an end date that needs periodic updates to stay in the future.

### Dependency testing

The project tests against multiple combinations:
- Python versions: 3.11, 3.12, 3.13, 3.14
- psutil versions: 5.9 (minimum) and latest
- python-dateutil versions: 2.8 (minimum) and latest
- tzlocal versions: <3, >3,<5, and >4

This is configured in `tox.ini` matrix testing.

## Code style

- Linting: Ruff with strict rules including docstrings (Google style), type annotations, security checks
- Formatting: Black (88 char line length) and isort
- Type checking: mypy with strict settings (`disallow_untyped_defs`, `check_untyped_defs`)
- Docstrings: Google style, required on all public functions/classes (D1 rules ignored for simplicity)
- Assertions: Used for documentation and debugging (S101 allowed)

## Writing style

- One line per sentence in markdown and reStructured text documents
- No unnecessary text formatting such as bold face or italics.
- No wordy text.
  Be precise and to the point.
- Headlines do not use title case.
  Only the first character of each headline is capitalized.

## Configuration

The daemon reads a config file with sections for each check.
Each check:
1. Implements `create()` class method to instantiate from config
2. Defines parameter schema via `ParameterSchemaAware`
3. Implements `check()` method (Activity) or `check(timestamp)` method (Wakeup)

Configuration validation is strict and raises `ConfigurationError` for invalid settings.

## CI/CD

- Conventional Commits: Uses commitlint (v21+) to enforce conventional commit format
- Semantic Release: Automated versioning based on commit messages
- Code coverage: Reported to codecov.io
- Documentation: Built and published on each push to main

## Common issues

- Test data expiration: iCal test files with hardcoded dates will fail when the event end date passes the current date.
  Update `DTEND` in `.ics` files to extend into the future.
- Timezone handling: The project carefully handles timezones, especially with DST transitions.
  Use `freezegun` with `tz_offset` parameter in tests that depend on specific timezone behavior.
- D-Bus dependencies: Some checks require D-Bus and system libraries.
  The CI installs these via `libdbus-1-dev`, `libgirepository-2.0-dev`.
