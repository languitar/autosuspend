Available checks
----------------

The following checks for activity are currently implemented.
Each of the is described with its available configuration options and required optional dependencies.

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

Smb
~~~

.. program:: check-smb

Any active Samba connection will block suspend.

Options
^^^^^^^

Requirements
^^^^^^^^^^^^

.. option:: smbstatus

   executable needs to be present.

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

Load
~~~~

.. program:: check-load

Checks whether the system load 5 is below a certain value.

Options
^^^^^^^

.. option:: threshold

   a float for the maximum allowed load value, default: 2.5

Requirements
^^^^^^^^^^^^

XIdleTime
~~~~~~~~~

.. program:: check-xidletime

Checks whether all active local X displays have been idle for a sufficiently long time.
This assumes a recent operating system where the X server is started with user permissions (i.e. not as root).

Options
^^^^^^^

.. option:: timeout

   required idle time in seconds

.. option:: ignore_if_process

   a regular expression to match against the process names executed by each X session owner.
   In case the use has a process running, which matches against this expression, the X idle time is ignore and the check continues as if there was no activity.
   This can be useful in case of processes which inevitabl
