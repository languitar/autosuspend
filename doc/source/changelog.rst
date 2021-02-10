Changelog
#########

|project| follows `Semantic Versioning <https://semver.org/>`_.
Hence, any breaking change to the configuration, command line interface, `systemd`_
interface, etc. will result in a new major release of |project|.

Pending
*******

New features
============

New activity checks
-------------------

* :ref:`check-jsonpath`: Similar to the existing :ref`check-xpath`, the new checks requests a JSON URL and evaluates it against a `JSONPath`_ expression to determine activity (:issue:`81`).
* :ref:`check-last-log-activity`: Check log files for most recent contained timestamps (:issue:`98`, :issue:`99`).

Fixed bugs
==========

* Connection errors are now properly handled by :ref:`check-mpd` (:issue:`77`).

Notable changes
===============

* The required `Python`_ version is now declared in the :ref:`installation` and :file:`setup.py` (:issue:`76`)
* Python 3.9 is officially supported and tested (:issue:`89`).
* Some code cleanup work has been performed (:issue:`93` and :issue:`92`).
* The daemon now better distinguished between temporary and permanent issues, for instance, by terminating in case a required program is not installed (:issue:`78`).

3.0
***

This version splits the executable into two distinct subcommands, one for activity checking and one for scheduling wake ups.
This way, the wake up scheduling mechanism can be hooked into system tools such as `systemd`_ to ensure that wake ups are scheduled correctly every time the system suspends.
This increases the reliability of the mechanism but also changes the way |project_program| has to be called.
You now need to enable two `systemd`_ units as describe in :ref:`systemd-integration` and the command line interface has changed.

New features
============

* The :ref:`check-kodi-idle-time` activity check can now be parameterized whether to indicate activity on a paused player or not (:issue:`59`, :issue:`60`).
* New structure as described above in the version introduction (:issue:`43`).

Fixed bugs
==========

* Documented default URL for the ``Kodi*`` checks did not actually exist in code, which has been fixed now (:issue:`58`, :issue:`61`).
* A bug in :ref:`check-logind-session-idle` has been fixed (:issue:`71`, :issue:`72`).

Notable changes
===============

* The executable now uses subcommands.
  The previous behavior as a long-running daemon is now available under the ``daemon`` subcommand.
* The command line flags for logging have changed.
  The previous ``-l`` flag, which combined boolean behavior and file reading, has been split into two distinct flags: ``-d`` is a boolean switch to enable full debug logging to console, whereas the old ``-l`` is now only used for reading logging configuration files.
  This change prevents nasty subtleties and issues when parsing the command line and became mandatory to support subcommands after the general configuration arguments such as logging.
* Dropped support for Python 3.6 and included Python 3.8 in CI infrastructure.
  Everything works on Python 3.8.
* The documentation has been restructured and improved. For instance, there is now a :ref:`faq` section.
* Some build and test dependencies have changed.
* CI-builds have been converted to Github Actions.

2.0.4
*****

This is a minor bug fix release.

Fixed bugs
==========

* :ref:`check-active-connection` did not handle local IPv6 addresses with scope such as ``fe80::5193:518c:5c69:aedb%enp3s0`` (:issue:`50`)

2.0.3
*****

This is a minor bug fix release.

Fixed bugs
==========

* :ref:`check-network-bandwidth` did not update its internal state and therefore did not work as documented (:issue:`49`)

2.0.2
*****

This is a minor bug fix release.

Fixed bugs
==========

* :ref:`check-kodi` and :ref:`check-kodi-idle-time` checks now catch ``JSONDecodeErrors`` (:issue:`45`)
* :ref:`check-kodi` and :ref:`check-kodi-idle-time` checks now support authentication (:issue:`47`)

2.0
***

This version adds scheduled wake ups as its main features.
In addition to checks for activity, a set of checks for future activities can now be configured to determine times at which the systems needs to be online again.
The daemon will start suspending in case the next detected wake up time is far enough in the future and schedule an automatic system wake up at the closest determined wake up time.
This can, for instance, be used to ensure that the system is up again when a TV show has to be recorded to disk.

Below is a detailed list of notable changes.

New features
============

* Scheduled wake ups (:issue:`9`).
* Ability to call configurable user commands before suspending for notification purposes (:issue:`25`).
* Checks using network requests now support authentication (:issue:`32`).
* Checks using network requests now support ``file://`` URIs (:issue:`36`).

New activity checks
-------------------

* :ref:`check-active-calendar-event`: Uses an `iCalendar`_ file (via network request) to prevent suspending in case an event in the calendar is currently active (:issue:`24`).
* :ref:`check-kodi-idle-time`: Checks the idle time of `Kodi`_ to prevent suspending in case the menu is used (:issue:`33`).

New wakeup checks
-----------------

* :ref:`wakeup-calendar`: Wake up the system at the next event in an `iCalendar`_ file (requested via network, :issue:`30`).
* :ref:`wakeup-command`: Call an external command to determine the next wake up time (:issue:`26`).
* :ref:`wakeup-file`: Read the next wake up time from a file (:issue:`9`).
* :ref:`wakeup-periodic`: Wake up at a defined interval, for instance, to refresh calendars for the :ref:`wakeup-calendar` check (:issue:`34`).
* :ref:`wakeup-xpath` and :ref:`wakeup-xpath-delta`: Request an XML document and use `XPath`_ to extract the next wakeup time.

Fixed bugs
==========

* `XPath`_ checks now support responses with explicit encodings (:issue:`29`).

Notable changes
===============

* The namespace of the logging systems has been rearranged (:issue:`38`).
  Existing logging configurations might require changes.
* The default configuration file has been reduced to explain the syntax and semantics.
  For a list of all available checks, refer the manual instead (:issue:`39`).

For a complete list of all addressed issues and new features, please refer to the respective `Github milestone <https://github.com/languitar/autosuspend/issues?utf8=%E2%9C%93&q=is%3Aissue+milestone%3A2.0>`_.
