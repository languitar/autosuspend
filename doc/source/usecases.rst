Common use cases
================

This page lists hints and configurations for common use cases.

Keeping a system active at daytime
----------------------------------

Imagine you want to have a NAS that is always available between 7 a.m. and 8 p.m.
After 8 p.m. the system should go to sleep in case no one else is using it.
Every morning at 7 a.m. it should wake up automatically.
This workflow can be realized using the ``Calendar`` wakeup check and the ``ActiveCalendarEvent`` activity check based on an `iCalendar`_ file residing on the local file system of the NAS.
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
