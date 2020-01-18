Changelog
=========

3.0
---

New features
~~~~~~~~~~~~

* The :ref:`check-kodi-idle-time` activity check can now be parameterized whether to indicate activity on a paused player or not (:issue:`59`, :issue:`60`).

Fixed bugs
~~~~~~~~~~

* Documented default URL for the ``Kodi*`` checks did not actually exist in code, which has been fixed now (:issue:`58`, :issue:`61`).

Notable changes
~~~~~~~~~~~~~~~

* The executable now uses subcommands.
  The previous behavior as a long-running daemon is now available under the ``daemon`` subcommand.
* The command line flags for logging have changed.
  The previous ``-l`` flag, which combined boolean behavior and file reading, has been split into two distinct flags: ``-d`` is a boolean switch to enable full debug logging to console, whereas the old ``-l`` is now only used for reading logging configuration files.
  This change prevents nasty subtleties and issues when parsing the command line and became mandatory to support subcommands after the general configuration arguments such as logging.
* Dropped support for Python 3.6 and included Python 3.8 in CI infrastructure.
  Everything works on Python 3.8.

2.0.4
-----

This is a minor bug fix release.

Fixed bugs
~~~~~~~~~~

* :ref:`check-active-connection` did not handle local IPv6 addresses with scope such as ``fe80::5193:518c:5c69:aedb%enp3s0`` (:issue:`50`)

2.0.3
-----

This is a minor bug fix release.

Fixed bugs
~~~~~~~~~~

* :ref:`check-network-bandwidth` did not update its internal state and therefore did not work as documented (:issue:`49`)

2.0.2
-----

This is a minor bug fix release.

Fixed bugs
~~~~~~~~~~

* :ref:`check-kodi` and :ref:`check-kodi-idle-time` checks now catch ``JSONDecodeErrors`` (:issue:`45`)
* :ref:`check-kodi` and :ref:`check-kodi-idle-time` checks now support authentication (:issue:`47`)

2.0
---

This version adds scheduled wake ups as its main features.
In addition to checks for activity, a set of checks for future activities can now be configured to determine times at which the systems needs to be online again.
The daemon will start suspending in case the next detected wake up time is far enough in the future and schedule an automatic system wake up at the closest determined wake up time.
This can, for instance, be used to ensure that the system is up again when a TV show has to be recorded to disk.

Below is a detailed list of notable changes.

New features
~~~~~~~~~~~~

* Scheduled wake ups (:issue:`9`).
* Ability to call configurable user commands before suspending for notification purposes (:issue:`25`).
* Checks using network requests now support authentication (:issue:`32`).
* Checks using network requests now support ``file://`` URIs (:issue:`36`).

New activity checks
^^^^^^^^^^^^^^^^^^^

* :ref:`check-active-calendar-event`: Uses an `iCalendar`_ file (via network request) to prevent suspending in case an event in the calendar is currently active (:issue:`24`).
* :ref:`check-kodi-idle-time`: Checks the idle time of `Kodi`_ to prevent suspending in case the menu is used (:issue:`33`).

New wakeup checks
^^^^^^^^^^^^^^^^^

* :ref:`wakeup-calendar`: Wake up the system at the next event in an `iCalendar`_ file (requested via network, :issue:`30`).
* :ref:`wakeup-command`: Call an external command to determine the next wake up time (:issue:`26`).
* :ref:`wakeup-file`: Read the next wake up time from a file (:issue:`9`).
* :ref:`wakeup-periodic`: Wake up at a defined interval, for instance, to refresh calendars for the :ref:`wakeup-calendar` check (:issue:`34`).
* :ref:`wakeup-xpath` and :ref:`wakeup-xpath-delta`: Request an XML document and use `XPath`_ to extract the next wakeup time.

Fixed bugs
~~~~~~~~~~

* `XPath`_ checks now support responses with explicit encodings (:issue:`29`).

Notable changes
~~~~~~~~~~~~~~~

* The namespace of the logging systems has been rearranged (:issue:`38`).
  Existing logging configurations might require changes.
* The default configuration file has been reduced to explain the syntax and semantics.
  For a list of all available checks, refer the manual instead (:issue:`39`).

For a complete list of all addressed issues and new features, please refer to the respective `Github milestone <https://github.com/languitar/autosuspend/issues?utf8=%E2%9C%93&q=is%3Aissue+milestone%3A2.0>`_.
