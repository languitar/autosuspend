Syntax
~~~~~~

The |project_program| configuration file uses INI syntax and needs to be processable by the Python `configparser`_ module.

A simple configuration file could look like:

.. code-block:: ini

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

The configuration file consists of a ``[general]`` section, which specifies general processing options, and multiple options of the format ``[check.*]``.
These sections describe the checks to execute to determine inactivity.

General Configuration
~~~~~~~~~~~~~~~~~~~~~

.. program:: config-general

The ``[general]`` section contains options controlling the overall behavior of the |project_program| daemon. These are:

.. option:: interval

   The time to wait after executing all checks in seconds.

.. option:: idle_time

   The required amount of time in seconds with no detected activity before the host will be suspended.

.. option:: suspend_cmd

   The command to execute in case the host shall be suspended.
   This line can contain additional command line arguments to the command to execute.

Check Configuration
~~~~~~~~~~~~~~~~~~~

.. program:: config-check

For each check to execute, a section with the name format ``[check.*]`` needs to be created.
Each check has a name and an executing class which implements the behavior.
The fraction of the section name ``check.`` determines the name, and in case no class option is given inside the section, also the class which implements the check.
In case the `option:`class` option is specified, the name is completely user-defined and the same check can even be instantiated multiple times with differing names.

For each check, these generic options can be specified:

.. option:: class

   Name of the class implementing the check.
   If this is not specified, the section name must represent a valid check class (see list below).

.. option:: enabled

   Needs to be ``true`` for a check to actually execute.
   ``false`` is assumed if not specified.

Furthermore, each check might have custom options.
