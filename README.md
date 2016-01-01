# autosuspend

`autosuspend` is a python daemon that suspends a system if certain conditions are met, or not met. This enables a server to sleep in case of inactivity without depending on the X infrastructure usually used by normal desktop environments.

`autosuspend` started as a fork of [Merlin Schumacher's version](https://github.com/merlinschumacher/autosuspend) but has since then been overhauled completely.

## Requirements

* [Python](https://www.python.org/) version 3
* [psutil](https://github.com/giampaolo/psutil)

Furthermore, specific checks might have additional dependencies. Have a look at the check documentation for hints in this direction.

## Concept

`autosuspend` periodically iterates a number of user-configurable checks, which shall indicate whether a certain activity on the host is currently present that should prevent the host from suspending. In case one of the checks indicates such activity, no action is taken and periodic checking continues. Otherwise, in case no activity can be detected, this state needs to be present for a specified amount of time before the host is suspended by `autosuspend`.

## Configuration

`autosuspend` is configured using an INI-like configuration file, compatible with [Python's configparser module](https://docs.python.org/3/library/configparser.html). If the daemon is installed in the standard file system layout, this file is `/etc/autosuspend.conf`. This configuration file might look like this:

```ini
[general]
interval = 30
idle_time = 900
suspend_cmd = /usr/bin/systemctl suspend

[check.Ping]
enabled = false
hosts = 192.168.0.7

[check.RemoteUsers]
class = Users
enabled = true
name = .*
terminal = .*
host = [0-9].*

[check.LocalUsers]
class = Users
enabled = false
name = .*
terminal = .*
host = localhost
```

### General Configuration

The `general` section contains options controlling the overall behavior of the `autosuspend` daemon. These are:

* `interval`: the time to wait after executing all checks in seconds
* `idle_time`: the required amount of time with no detected activity before the host will be suspended
* `suspend_cmd`: the command to execute in case the host shall be suspended

### Check Configuration

For each check to execute, a section with the name format `check.*` needs to be created. Each check has a name and an executing class which implements the behavior. The fraction of the section name after `check.` determines the name, and in case no `class` option is given inside the section, also the class which implements the check. In case a `class` option is specified, the name is completely user-defined and the same check can even be instantiated multiple times with differing names.

For each check, these generic options can be specified:
* `class`: name of the class implementing the check. If this is not specified, the section name must represent a valid class.
* `enabled`: Need to be `true` for a check to actually execute. `false` is assumed if not specified.

Furthermore, each check might have custom options. These are outlined below.

## Usage

The daemon usually needs to be executed as `root` so that all necessary pieces of information can be gathered.

```
usage: autosuspend.py [-h] [-c FILE] [-a] [-l [FILE]]

Automatically suspends a server based on several criteria

optional arguments:
  -h, --help            show this help message and exit
  -c FILE, --config FILE
                        The config file to use (default: <_io.TextIOWrapper
                        name='/etc/autosuspend.conf' mode='r'
                        encoding='UTF-8'>)
  -a, --allchecks       Execute all checks even if one has already prevented
                        the system from going to sleep. Useful to debug
                        individual checks. (default: False)
  -l [FILE], --logging [FILE]
                        Configures the python logging system. If used without
                        an argument, all logging is enabled to the console. If
                        used with an argument, the configuration is read from
                        the specified file. (default: False)
```

The package ships with a [service definition file](http://www.freedesktop.org/software/systemd/man/systemd.service.html) for [systemd](https://wiki.freedesktop.org/www/Software/systemd/), so that you should be able to launch it via systemd using e.g.:

```
systemd enable autosuspend.service
systemd start autosuspend.service
```

## Available Checks

### Ping

Checks whether one or more hosts answer to ICMP requests.

#### Options

* `hosts`: Comma-separated list of host names or IPs.

#### Requirements

### Mpd

Checks whether an instance of [MPD](http://www.musicpd.org/) is currently playing music.

#### Options

* `host`: Host containing the MPD daemon, default: `localhost`
* `port`: Port to connect to the MPD daemon, default: `6600`

#### Requirements

* [python-mpd2](https://pypi.python.org/pypi/python-mpd2)

### Users

Checks whether a user currently logged in at the system matches several criteria. All provided criteria must match to indicate activity on the host.

#### Options

All regular expressions are applied against the full string. Capturing substrings needs to be explicitly enabled using wildcard matching.

* `name`: A regular expression specifying which users to capture, default: `.*`.
* `terminal`: A regular expression specifying the terminal on which the user needs to be logged in, default: `.*`.
* `host`: A regular expression specifying the host from which a user needs to be logged in, default: `.*`.

#### Requirements

### Smb

Any active Samba connection will block suspend.

#### Options

#### Requirements

* `smbstatus` executable needs to be present.

### Processes

If currently running processes match an expression, the suspend will be blocked. You might use this to hinder the system from suspending when for example your rsync runs

#### Options

* `processes`: list of comma-separated process names to check for

#### Requirements

### ActiveConnection

Checks whether there is currently a client connected to a TCP server at certain ports. Can be used to e.g. block suspending the system in case SSH users are connected or a web server is used by clients.

#### Options

* `ports`: list of comma-separated port numbers

#### Requirements

### Load

Checks whether the system load 5 is below a certain value.

#### Options

* `threshold`: a float for the maximum allowed load value, default: 2.5

#### Requirements

### XIdleTime

Checks whether all active local X displays have been idle for a sufficiently long time.

#### Options

* `timeout`: required idle time in seconds

#### Requirements

## Debugging

In case you need to track configuration issues to understand why a system goes to suspend or does not, the extensive logging output might be used. The command line flag `-l` allows to specify a [Python logging config file](https://docs.python.org/3/library/logging.config.html) to specify what to log. The provided systemd service file already uses `/etc/autosuspend-logging.cong` per default. Each iteration logs exactly which condition detected activity or not. So you should be able to find out what is going on.

In case one of the conditions you monitor prevents sleeping the system in case of an external connection (logged-in users, open TCP port), then the logging configuration might be changed to use the [broadcast-logging](https://github.com/languitar/broadcast-logging) package. This way, the server will broadcast new log messages and external clients on the same network can listen to these messages without creating an explicit connection. Please refer to the documentation of the broadcast-logging package on how to enable and use it.

## License

This software is licensed using the [GPL2 license](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html).
