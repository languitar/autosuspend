Debugging
=========

In case you need to track configuration issues to understand why a system suspends or does not, the extensive logging output of |project_program| might be used.
The command line flag :option:`autosuspend -l` allows to specify a Python logging configuration file which specifies what to log.
The provided `systemd`_ service files (see :ref:`systemd-integration`) already use :file:`/etc/autosuspend-logging.conf` as the standard location and a default file is usually installed.
Each iteration logs exactly which condition detected activity or not.
So you should be able to find out what is going on.

In case one of the conditions you monitor prevents suspending the system if an external connection is established (logged-in users, open TCP port), then the logging configuration file can be changed to use the `broadcast-logging`_ package.
This way, the server will broadcast new log messages on the network and external clients on the same network can listen to these messages without creating an explicit connection.
Please refer to the documentation of the `broadcast-logging`_ package on how to enable and use it.
Additionally, one might also examine the ``journalctl`` for |project_program| after the fact.
