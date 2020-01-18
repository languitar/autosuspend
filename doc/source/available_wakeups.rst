.. _available-wakeups:

Available wake up checks
------------------------

The following checks for wake up times are currently implemented.
Each of the checks is described with its available configuration options and required optional dependencies.

.. _wakeup-calendar:

Calendar
~~~~~~~~

.. program:: wakeup-calendar

Determines next wake up time from an `iCalendar`_ file.
The next event that starts after the current time is chosen as the next wake up time.

Remember that updates to the calendar can only be reflected in case the system currently running.
Changes to the calendar made while the system is sleeping will obviously not trigger an earlier wake up.

Options
^^^^^^^

.. option:: url

   The URL to query for the XML reply.

.. option:: username

   Optional user name to use for authenticating at a server requiring authentication.
   If used, also a password must be provided.

.. option:: password

   Optional password to use for authenticating at a server requiring authentication.
   If used, also a user name must be provided.

.. option:: xpath

   The XPath query to execute.
   Must always return number strings or nothing.

.. option:: timeout

   Timeout for executed requests in seconds. Default: 5.


Requirements
^^^^^^^^^^^^

* `requests`_
* `icalendar <python-icalendar_>`_
* `dateutil`_
* `tzlocal`_

.. _wakeup-command:

Command
~~~~~~~

.. program:: wakeup-command

Determines the wake up time by calling an external command
The command always has to succeed.
If something is printed on stdout by the command, this has to be the next wake up time in UTC seconds.

The command is executed as is using shell execution.
Beware of malicious commands in obtained configuration files.

Options
^^^^^^^

.. option:: command

   The command to execute including all arguments

.. _wakeup-file:

File
~~~~

.. program:: wakeup-file

Determines the wake up time by reading a file from a configured location.
The file has to contains the planned wake up time as an int or float in seconds UTC.

Options
^^^^^^^

.. option:: path

   path of the file to read in case it is present

.. _wakeup-periodic:

Periodic
~~~~~~~~

.. program:: wakeup-periodic

Always schedules a wake up at a specified delta from now on.
Can be used to let the system wake up every once in a while, for instance, to refresh the calendar used in the :ref:`wakeup-calendar` check.

Options
^^^^^^^

.. option:: unit

   A string indicating in which unit the delta is specified.
   Valid options are: ``microseconds``, ``milliseconds``, ``seconds``, ``minutes``, ``hours``, ``days``, ``weeks``.

.. option:: value

   The value of the delta as an int.

.. _wakeup-xpath:

XPath
~~~~~

.. program:: wakeup-xpath

A generic check which queries a configured URL and expects the reply to contain XML data.
The returned XML document is parsed using a configured `XPath`_ expression that has to return timestamps UTC (as strings, not elements).
These are interpreted as the wake up times.
In case multiple entries exist, the soonest one is used.

Options
^^^^^^^

.. option:: url

   The URL to query for the XML reply.

.. option:: xpath

   The XPath query to execute.
   Must always return number strings or nothing.

.. option:: timeout

   Timeout for executed requests in seconds. Default: 5.

.. option:: username

   Optional user name to use for authenticating at a server requiring authentication.
   If used, also a password must be provided.

.. option:: password

   Optional password to use for authenticating at a server requiring authentication.
   If used, also a user name must be provided.

.. _wakeup-xpath-delta:

XPathDelta
~~~~~~~~~~

.. program:: wakeup-xpath-delta

Comparable to :ref:`wakeup-xpath`, but expects that the returned results represent the wake up time as a delta to the current time in a configurable unit.

This check can for instance be used for `tvheadend`_ with the following expression::

    //recording/next/text()

Options
^^^^^^^

.. option:: url

   The URL to query for the XML reply.

.. option:: username

   Optional user name to use for authenticating at a server requiring authentication.
   If used, also a password must be provided.

.. option:: password

   Optional password to use for authenticating at a server requiring authentication.
   If used, also a user name must be provided.

.. option:: xpath

   The XPath query to execute.
   Must always return number strings or nothing.

.. option:: timeout

   Timeout for executed requests in seconds. Default: 5.

.. option:: unit

   A string indicating in which unit the delta is specified.
   Valid options are: ``microseconds``, ``milliseconds``, ``seconds``, ``minutes``, ``hours``, ``days``, ``weeks``.
   Default: minutes
