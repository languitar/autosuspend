Changelog
=========

2.0.2
-----

This is a minor bug fix release.

Fixes bugs
~~~~~~~~~~

* ``Kodi`` and ``KodiIdleTime`` checks now catch ``JSONDecodeErrors`` (:issue:`45`)
* ``Kodi`` and ``KodiIdleTime`` checks now support authentication (:issue:`47`)

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

* ``ActiveCalendarEvent``: Uses an `iCalendar`_ file (via network request) to prevent suspending in case an event in the calendar is currently active (:issue:`24`).
* ``KodiIdleTime``: Checks the idle time of `Kodi`_ to prevent suspending in case the menu is used (:issue:`33`).

New wakeup checks
^^^^^^^^^^^^^^^^^

* ``Calendar``: Wake up the system at the next event in an `iCalendar`_ file (requested via network, :issue:`30`).
* ``Command``: Call an external command to determine the next wake up time (:issue:`26`).
* ``File``: Read the next wake up time from a file (:issue:`9`).
* ``Periodic``: Wake up at a defined interval, for instance, to refresh calendars for the ``Calendar`` check (:issue:`34`).
* ``XPath`` and ``XPathDelta``: Request an XML document and use `XPath`_ to extract the next wakeup time.

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
