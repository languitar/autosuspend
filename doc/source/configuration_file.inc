Syntax
~~~~~~

The |project_program| configuration file uses INI syntax and needs to be processable by the Python `configparser`_ module.

A simple configuration file could look like:

.. code-block:: ini

   [general]
   interval = 30
   idle_time = 900
   suspend_cmd = /usr/bin/systemctl suspend
   wakeup_cmd = echo {timestamp:.0f} > /sys/class/rtc/rtc0/wakealarm
   notify_cmd_wakeup = su myuser -c notify-send -a autosuspend 'Suspending the system. Wake up at {iso}'
   notify_cmd_no_wakeup = su myuser -c notify-send -a autosuspend 'Suspending the system.'
   
   [check.Ping]
   enabled = false
   hosts = 192.168.0.7
   
   [check.RemoteUsers]
   class = Users
   enabled = true
   name = .*
   terminal = .*
   host = [0-9].*
   
   [wakeup.WakeupFile]
   enabled = True
   path = /var/run/autosuspend/wakeup

The configuration file consists of a ``[general]`` section, which specifies general processing options, and multiple sections of the format ``[check.*]`` and ``[wakeup.*]``.
These sections describe the activity and wake up checks to execute.

General configuration
~~~~~~~~~~~~~~~~~~~~~

.. program:: config-general

The ``[general]`` section contains options controlling the overall behavior of the |project_program| daemon. These are:

.. option:: interval

   The time to wait after executing all checks in seconds.

.. option:: idle_time

   The required amount of time in seconds with no detected activity before the host will be suspended.
   Default: 300 seconds

.. option:: min_sleep_time

   The minimal amount of time in seconds the system has to sleep for actually triggering suspension.
   If a scheduled wake up results in an effective time below this value, the system will not sleep.
   Default: 1200 seconds

.. option:: wakeup_delta

   Wake up the system this amount of seconds earlier than the time that was determined for an event that requires the system to be up.
   This value adds a safety margin for the time a the wake up effectively takes.
   Default: 30 seconds

.. option:: suspend_cmd

   The command to execute in case the host shall be suspended.
   This line can contain additional command line arguments to the command to execute.

.. option:: wakeup_cmd

   The command to execute for scheduling a wake up of the system.
   The given string is processed using Python's :meth:`str.format` and a format argument called ``timestamp`` encodes the UTC timestamp of the planned wake up time (float).
   Additionally ``iso`` can be used to acquire the timestamp in ISO 8601 format.

.. option:: notify_cmd_wakeup

   A command to execute before the system is going to suspend for the purpose of notifying interested clients.
   This command is only called in case a wake up is scheduled.
   The given string is processed using Python's :meth:`str.format` and a format argument called ``timestamp`` encodes the UTC timestamp of the planned wake up time (float).
   Additionally ``iso`` can be used to acquire the timestamp in ISO 8601 format.
   If empty or not specified, no command will be called.

.. option:: notify_cmd_no_wakeup

   A command to execute before the system is going to suspend for the purpose of notifying interested clients.
   This command is only called in case NO wake up is scheduled.
   Hence, no string formatting options are available.
   If empty or not specified, no command will be called.

.. option:: woke_up_file

   Location of a file that indicates to |project_program| that the computer has suspended since the last time checks were executed.
   This file is usually created by a `systemd`_ service.
   Thus, changing the location also requires adapting the respective service.
   Refer to :ref:`systemd-integration` for further details.

Activity check configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. program:: config-check

For each activity check to execute, a section with the name format ``[check.*]`` needs to be created.
Each check has a name and an executing class which implements the behavior.
The fraction of the section name ``check.`` determines the name, and in case no class option is given inside the section, also the class which implements the check.
In case the :option:`class` option is specified, the name is completely user-defined and the same check can even be instantiated multiple times with differing names.

For each check, these generic options can be specified:

.. option:: class

   Name of the class implementing the check.
   If this is not specified, the section name must represent a valid check class (see list below).

.. option:: enabled

   Needs to be ``true`` for a check to actually execute.
   ``false`` is assumed if not specified.

Furthermore, each check might have custom options.

Wake up check configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Wake up checks uses the same configuration logic as the previously described activity checks.
However, the configuration file sections start with ``wakeup.`` instead of ``check.``.
