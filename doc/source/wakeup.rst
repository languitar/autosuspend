On-demand wakeup
================

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

A set of front-ends for various platforms allows to send the magic packets. For instance:

* `gWakeOnLan <http://www.muflone.com/gwakeonlan/english/>`__: GTK GUI, Linux
* `wol <https://sourceforge.net/projects/wake-on-lan/>`__: command line, Linux
* `Wake On Lan <https://sourceforge.net/projects/aquilawol/>`__: GUI, Windows
* `Wake On Lan <https://play.google.com/store/apps/details?id=co.uk.mrwebb.wakeonlan>`__: Android
* `Wake On Lan <https://f-droid.org/en/packages/net.mafro.android.wakeonlan/>`__: Android, open-source
* `Kore (Kodi remote control) <https://play.google.com/store/apps/details?id=org.xbmc.kore>`__: Android, for Kodi users
* `Mocha WOL <https://itunes.apple.com/de/app/mocha-wol/id422625778>`__: iOS
