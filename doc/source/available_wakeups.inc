Available wake up checks
------------------------

The following checks for wake up times are currently implemented.
Each of the checks is described with its available configuration options and required optional dependencies.

WakeupFile
~~~~~~~~~~

.. program:: wakeup-file

Determines the wake up time by reading a file from a configured location.
The file has to contains the planned wake up time as an int or float in seconds UTC.

Options
^^^^^^^

.. option:: path

   path of the file to read in case it is present

WakeupXPath
~~~~~~~~~~~

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

WakeupXPathDelta
~~~~~~~~~~~~~~~~

.. program:: wakeup-xpath-delta

Comparable to ``WakeupXPath``, but expects that the returned results represent the wake up time as a delta to the current time in a configurable unit.

This check can for instance be used for `tvheadend`_ with the following expression::

    //recording/next/text()

Options
^^^^^^^

.. option:: url

   The URL to query for the XML reply.

.. option:: xpath

   The XPath query to execute.
   Must always return number strings or nothing.

.. option:: timeout

   Timeout for executed requests in seconds. Default: 5.

.. option:: unit

   A string indicating in which unit the delta is specified.
   Valid options are: ``microseconds``, ``milliseconds``, ``seconds``, ``minutes``, ``hours``, ``days``, ``weeks``.
   Default: minutes
