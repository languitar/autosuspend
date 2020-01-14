.. _systemd-integration:

systemd integration
===================

Even though it is possible to run |project_program| manually (cf. :ref:`the manpage <man-command>`), in production use cases, the daemon will usually be run from `systemd`_.
For this purpose, the package ships with `service definition files <systemd service files>`_ for `systemd`_, so that you should be able to manage |project_program| via `systemd`_.
These files need to be installed in the appropriate locations for such service files, which depend on the Linux distribution.
Some common locations are:

* :file:`/usr/lib/systemd/system` (e.g. Archlinux packaged service files)
* :file:`/lib/systemd/system` (e.g. Debian packaged service files)
* :file:`/etc/systemd/system` (e.g. Archlinux manually added service files)

Binary installation packages for Linux distributions should have installed the service files at the appropriate locations already.

To start |project_program| via `systemd`_, execute:

.. code-block:: bash

   systemctl enable autosuspend.service
   systemctl enable autosuspend-detect-suspend.service

.. note::

   Do not forget the second ``enable`` call to ensure that wake ups are configured even if the system is manually placed into suspend.

To start |project_program| automatically at system start, execute:

.. code-block:: bash

   systemctl start autosuspend.service
