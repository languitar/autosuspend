.. _faq:

Frequently Asked Questions
##########################

Usage
*****

How to check unsupported software?
==================================

In case you want to detect if some piece of software running on your system that is not officially supported is performing relevant activity you have two options:

* Use a script with the :ref:`check-external-command` check.

* Implement a Python module with you check being a subclass of
  :class:`autosuspend.checks.Activity` or
  :class:`autosuspend.checks.Wakeup` and install it alongside |project|.
  The custom check class can then be referenced in the config with its full dotted path, for instance, ``mymodule.MyCheck``, in the `class` field.

How do I wake up my system if needed?
=====================================

|project_bold| itself only handles wake ups for events that were foreseeable at the time the system was put into sleep mode.
In case the system also has to be used on-demand, a simple way to wake up the system is to enable `Wake on LAN <https://en.wikipedia.org/wiki/Wake-on-LAN>`_.
Here, a special network packet can be used to wake up the system again.
Multiple front-ends exist to send these magic packets.
The typical usage scenario with this approach is to manually send the magic packet when the system is needed, wait a few seconds, and then to perform the intended tasks with the system.

Wake on LAN needs to be specifically enabled on the system.
Typically, the documentation of common Linux distributions explains how to enable Wake on LAN:

* `Archlinux <https://wiki.archlinux.org/index.php/Wake-on-LAN>`__
* `Debian <https://wiki.debian.org/WakeOnLan>`__
* `Ubuntu <https://help.ubuntu.com/community/WakeOnLan>`__

A set of front-ends for various platforms allows sending the magic packets.
For instance:

* `gWakeOnLan <http://www.muflone.com/gwakeonlan/english/>`__: GTK GUI, Linux
* `wol <https://sourceforge.net/projects/wake-on-lan/>`__: command line, Linux
* `Wake On Lan <https://sourceforge.net/projects/aquilawol/>`__: GUI, Windows
* `Wake On Lan <https://play.google.com/store/apps/details?id=co.uk.mrwebb.wakeonlan>`__: Android
* `Wake On Lan <https://f-droid.org/en/packages/net.mafro.android.wakeonlan/>`__: Android, open-source
* `Kore (Kodi remote control) <https://play.google.com/store/apps/details?id=org.xbmc.kore>`__: Android, for Kodi users
* `Mocha WOL <https://itunes.apple.com/de/app/mocha-wol/id422625778>`__: iOS

How do I keep a system active at daytime
========================================

Imagine you want to have a NAS that is always available between 7 a.m. and 8 p.m.
After 8 p.m. the system should go to sleep in case no one else is using it.
Every morning at 7 a.m. it should wake up automatically.
This workflow can be realized using the :ref:`wakeup-calendar` wakeup check and the :ref:`check-active-calendar-event` activity check based on an `iCalendar`_ file residing on the local file system of the NAS.
The former check ensures that the system wakes up at the desired time of the day while the latter ensure that it stays active at daytime.

The first step is to create the `iCalendar`_ file, which can conveniently and graphically be edited with `Thunderbird Lightning <https://addons.thunderbird.net/de/thunderbird/addon/lightning/>`_ or any other calendar frontend.
Essentially, the ``*.ics`` may look like this::

   BEGIN:VCALENDAR
   PRODID:-//Mozilla.org/NONSGML Mozilla Calendar V1.1//EN
   VERSION:2.0
   BEGIN:VEVENT
   CREATED:20180602T151701Z
   LAST-MODIFIED:20180602T152732Z
   DTSTAMP:20180602T152732Z
   UID:0ef23894-702e-40ac-ab09-94fa8c9c51fd
   SUMMARY:keep active
   RRULE:FREQ=DAILY
   DTSTART:20180612T070000
   DTEND:20180612T200000
   TRANSP:OPAQUE
   SEQUENCE:3
   END:VEVENT
   END:VCALENDAR

Afterwards, edit ``autosuspend.conf`` to contain the two aforementioned checks based on the created ``ics`` file.
This will end up with at least this config:

.. code-block:: ini

   [general]
   interval = 30
   suspend_cmd = /usr/bin/systemctl suspend
   wakeup_cmd = echo {timestamp:.0f} > /sys/class/rtc/rtc0/wakealarm
   woke_up_file = /var/run/autosuspend-just-woke-up

   [check.ActiveCalendarEvent]
   enabled = true
   url = file:///path/to/your.ics

   [wakeup.Calendar]
   enabled = true
   url = file:///path/to/your.ics

Adding other activity checks will ensure that the system stays awake event after 8 p.m. if it is still used.

Error messages
**************

No connection adapters were found for '\file://\*'
==================================================

You need to install the `requests-file`_ package for ``file://`` URIs to work.
