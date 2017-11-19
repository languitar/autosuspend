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

To start |project_program| automatically at system start, execute:

.. code-block:: bash

   systemctl start autosuspend.service

Preventing the system from sleeping immediately after waking up
---------------------------------------------------------------

Unfortunately, |project_program| does not detect automatically if the system was placed into suspend mode manually.
Therefore, it might happen that after waking up again, all checks have indicated inactivity for a long time (the whole phase of sleeping) and |project_program| might initiate suspending again immediately.
To prevent this, `systemd`_ needs to inform |project_program| every time the system suspends.
This is achieved by a seconds service file, which needs to be enabled (not started):

.. code-block:: bash

   systemctl enable autosuspend-detect-suspend.service
