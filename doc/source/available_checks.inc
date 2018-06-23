Available activity checks
-------------------------

The following checks for activity are currently implemented.
Each of the is described with its available configuration options and required optional dependencies.

ActiveCalendarEvent
~~~~~~~~~~~~~~~~~~~

.. program:: check-active-calendar-event

Checks an online `iCalendar`_ file for events that are currently running.
If so, this indicates activity and prevents suspending the system.
Thus, a calendar can be provided with times at which the system should not go to sleep.
If this calendar resides on an online service like a groupware it might even be possible to invite the system.

Options
^^^^^^^

.. option:: url

   The URL to query for the iCalendar file

.. option:: timeout

   Timeout for executed requests in seconds. Default: 5.

.. option:: username

   Optional user name to use for authenticating at a server requiring authentication.
   If used, also a password must be provided.

.. option:: password

   Optional password to use for authenticating at a server requiring authentication.
   If used, also a user name must be provided.

Requirements
^^^^^^^^^^^^

* `requests`_
* `icalendar <python-icalendar_>`_
* `dateutil`_
* `tzlocal`_

ActiveConnection
~~~~~~~~~~~~~~~~

.. program:: check-active-connections

Checks whether there is currently a client connected to a TCP server at certain ports.
Can be used to e.g. block suspending the system in case SSH users are connected or a web server is used by clients.

Options
^^^^^^^

.. option:: ports

   list of comma-separated port numbers

Requirements
^^^^^^^^^^^^

ExternalCommand
~~~~~~~~~~~~~~~

.. program:: check-external-command

Executes an arbitrary command.
In case this command returns 0, the system is assumed to be active.

The command is executed as is using shell execution.
Beware of malicious commands in obtained configuration files.

Options
^^^^^^^

.. option:: command

   The command to execute including all arguments

Requirements
^^^^^^^^^^^^

Kodi
~~~~

.. program:: check-kodi

Checks whether an instance of `Kodi`_ is currently playing.

Options
^^^^^^^

.. option:: url

   Base URL of the JSON RPC API of the Kodi instance, default: ``http://localhost:8080/jsonrpc``

.. option:: timeout

   Request timeout in seconds, default: ``5``

Requirements
^^^^^^^^^^^^

-  `requests`_

KodiIdleTime
~~~~~~~~~~~~

.. program:: check-kodi-idle-time

Checks whether there has been interaction with the Kodi user interface recently.
This prevents suspending the system in case someone is currently browsing collections etc.
This check is redundant to ``XIdleTime`` on systems using an X server, but might be necessary in case Kodi is used standalone.
It does not replace the ``Kodi`` check, as the idle time is not updated when media is playing.

Options
^^^^^^^

.. option:: idle_time

   Marks the system active in case a user interaction has appeared within the this amount of seconds until now.
   Default: ``120``

.. option:: url

   Base URL of the JSON RPC API of the Kodi instance, default: ``http://localhost:8080/jsonrpc``

.. option:: timeout

   Request timeout in seconds, default: ``5``

Requirements
^^^^^^^^^^^^

-  `requests`_

Load
~~~~

.. program:: check-load

Checks whether the `system load 5 <https://en.wikipedia.org/wiki/Load_(computing)>`__ is below a certain value.

Options
^^^^^^^

.. option:: threshold

   a float for the maximum allowed load value, default: 2.5

Requirements
^^^^^^^^^^^^

LogindSessionsIdle
~~~~~~~~~~~~~~~~~~

.. program:: check-logind-idle

Prevents suspending in case ``IdleHint`` for one of the running sessions `logind`_ sessions is set to ``no``.
Support for setting this hint currently varies greatly across display managers, screen lockers etc.
Thus, check exactly whether the hint is set on your system via ``loginctl show-session``.

Options
^^^^^^^

.. option:: types

   A comma-separated list of sessions types to inspect for activity.
   The check ignores sessions of other types.
   Default: ``tty``, ``x11``, ``wayland``

.. option:: states

   A comma-separated list of session states to inspect.
   For instance, ``lingering`` sessions used for background programs might not be of interest.
   Default: ``active``, ``online``

Requirements
^^^^^^^^^^^^

-  `dbus-python`_

Mpd
~~~

.. program:: check-mpd

Checks whether an instance of `MPD`_ is currently playing music.

Options
^^^^^^^

.. option:: host

   Host containing the MPD daemon, default: ``localhost``

.. option:: port

   Port to connect to the MPD daemon, default: ``6600``

.. option:: timeout

   .. _mpd-timeout:

   Request timeout in seconds, default: ``5``

Requirements
^^^^^^^^^^^^

-  `python-mpd2`_


NetworkBandwidth
~~~~~~~~~~~~~~~~

.. program:: check-network-bandwidth

Checks whether more network bandwidth is currently being used than specified.
A set of specified interfaces is checked in this regard, each of the individually, based on the average bandwidth on that interface.
This average is based on the global checking interval specified in the configuration file via the :option:`interval <config-general interval>` option.

Options
^^^^^^^

.. option:: interfaces

   Comma-separated list of network interfaces to check

.. option:: threshold_send <byte/s>

   If the average sending bandwidth of one of the specified interfaces is above this threshold, then activity is detected. Specified in bytes/s, default: ``100``

.. option:: threshold_receive <byte/s>

   If the average receive bandwidth of one of the specified interfaces is above this threshold, then activity is detected. Specified in bytes/s, default: ``100``

Requirements
^^^^^^^^^^^^

Ping
~~~~

.. program:: check-ping

Checks whether one or more hosts answer to ICMP requests.

Options
^^^^^^^

.. option:: hosts

   Comma-separated list of host names or IPs.


Requirements
^^^^^^^^^^^^

Processes
~~~~~~~~~

.. program:: check-processes

If currently running processes match an expression, the suspend will be blocked.
You might use this to hinder the system from suspending when for example your rsync runs.

Options
^^^^^^^

.. option:: processes

   list of comma-separated process names to check for

Requirements
^^^^^^^^^^^^

Smb
~~~

.. program:: check-smb

Any active Samba connection will block suspend.

Options
^^^^^^^

.. option:: smbstatus

   executable needs to be present.

Requirements
^^^^^^^^^^^^

Users
~~~~~

.. program:: check-users

Checks whether a user currently logged in at the system matches several criteria.
All provided criteria must match to indicate activity on the host.

Options
^^^^^^^

All regular expressions are applied against the full string.
Capturing substrings needs to be explicitly enabled using wildcard matching.

.. option:: name

   A regular expression specifying which users to capture, default: ``.*``.

.. option:: terminal

   A regular expression specifying the terminal on which the user needs to be logged in, default: ``.*``.

.. option:: host

   A regular expression specifying the host from which a user needs to be logged in, default: ``.*``.

Requirements
^^^^^^^^^^^^

XIdleTime
~~~~~~~~~

.. program:: check-xidletime

Checks whether all active local X displays have been idle for a sufficiently long time.
Determining which X11 sessions currently exist on a running system is a harder problem than one might expect.
Sometimes, the server runs as root, sometimes under the real user, and many other configuration variants exist.
Thus, multiple sources for active X serer instances are implemented for this check, each of them having different requirements and limitations.
They can be changed using the provided configuration option.

Options
^^^^^^^

.. option:: timeout

   required idle time in seconds

.. option:: method

   The method to use for acquiring running X sessions.
   Valid options are ``sockets`` and ``logind``.
   The default is ``sockets``.

   ``sockets``
     Uses the X server sockets files found in :file:`/tmp/.X11-unix`.
     This method requires that all X server instances run with user permissions and not as root.
   ``logind``
     Uses `logind`_ to obtain the running X server instances.
     This does not support manually started servers.

.. option:: ignore_if_process

   A regular expression to match against the process names executed by each X session owner.
   In case the use has a running process that matches this expression, the X idle time is ignored and the check continues as if there was no activity.
   This can be useful in case of processes which inevitably tinker with the idle time.

.. option:: ignore_users

   Do not check sessions of users matching this regular expressions.

Requirements
^^^^^^^^^^^^

* `dbus-python`_ for the ``logind`` method

XPath
~~~~~

.. program:: check-xpath

A generic check which queries a configured URL and expects the reply to contain XML data.
The returned XML document is checked against a configured `XPath`_ expression and in case the expression matches, the system is assumed to be active.

Some common applications and their respective configuration are:

`tvheadend`_
    The required URL for `tvheadend`_ is (if running on the same host)::

        http://127.0.0.1:9981/status.xml

    In case you want to prevent suspending in case there are active subscriptions or recordings, use the following XPath::

        /currentload/subscriptions[number(.) > 0] | /currentload/recordings/recording/start

    If you have a permantently running subscriber like `Kodi`_, increase the ``0`` to ``1``.

`Plex`_
    For `Plex`_, use the following URL (if running on the same host)::

        http://127.0.0.1:32400/status/sessions/?X-Plex-Token={TOKEN}

    Where acquiring the token is `documented here <https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/>`_.

    If suspending should be prevented in case of any activity, this simple `XPath`_ expression will suffice::

        /MediaContainer[@size > 2]

Options
^^^^^^^

.. option:: url

   The URL to query for the XML reply.

.. option:: xpath

   The XPath query to execute.
   In case it returns a result, the system is assumed to be active.

.. option:: timeout

   Timeout for executed requests in seconds. Default: 5.

.. option:: username

   Optional user name to use for authenticating at a server requiring authentication.
   If used, also a password must be provided.

.. option:: password

   Optional password to use for authenticating at a server requiring authentication.
   If used, also a user name must be provided.

Requirements
^^^^^^^^^^^^

* `requests`_
* `lxml`_
