Available wake up checks
------------------------

The following checks for wake up times are currently implemented.
Each of the is described with its available configuration options and required optional dependencies.

WakeupFile
~~~~~~~~~~

.. program:: wakeup-file

Determines the wake up time by reading a file from a configured location.
The file has to contains the planned wake up time as an int or float in seconds UTC.

Options
^^^^^^^

.. option:: path

   path of the file to read in case it is present
