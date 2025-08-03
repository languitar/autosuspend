.. _installation:

Installation instructions
#########################

|project_program| is designed for Python **3** and does not work with Python 2.

.. note::

   After installation, do not forget to enable and start |project| vis `systemd`_ as described in :ref:`systemd-integration`.

Requirements
************

The minimal requirements are.

* `Python 3`_ >= 3.11
* `psutil`_
* `portalocker`_

Additionally, the some checks need further dependencies to function properly.
Please refer to :ref:`available-checks` for individual requirements.

If checks using URLs to load data should support ``file://`` URLs, `requests-file`_ is needed.

Binary packages
***************

.. image:: https://repology.org/badge/vertical-allrepos/autosuspend.svg
   :target: https://repology.org/project/autosuspend/versions

Debian
======

Installation from official package sources::

    apt-get install autosuspend

Archlinux (AUR)
===============

|project| is available as an `Archlinux AUR package <https://aur.archlinux.org/packages/autosuspend/>`_.

Installation via some `AUR helpers <https://wiki.archlinux.org/index.php/AUR_helpers>` such as :program:`paru`::

    paru -S autosuspend

Other AUR helpers may be used, too.

Gentoo
======

Patrick Holthaus has provided an ebuild for Gentoo in `his overlay <https://github.com/pholthau/pholthaus-overlay>`_.
You can use it as follows::

    eselect repository enable pholthaus-overlay
    emaint sync -r pholthaus-overlay
    emerge sys-apps/autosuspend

Other distributions
===================

In case you want to generate a package for a different Linux distribution, I'd be glad to hear about that.

Manual installation
*******************

|project_program| is a usual Python_ package and hence can be installed using the common Python_ packaging tools.
Briefly, the following steps can be used to install |project_program| from source in a system-wide location (as ``root`` user):

.. code-block:: bash

   python3 -m venv /opt/autosuspend
   /opt/autosuspend/bin/pip install git+https://github.com/languitar/autosuspend.git@<tag or branch>#egg=autosuspend[all]

.. note::

   Replace the angle brackets with desired Git tag or branch.
   Use ``main`` for the latest development release.

.. note::

   The ``all`` in the square brackets ensures that |project_program| is installed with all optional dependencies.
   That way all available checks can be used.
   In case you only need a subset of optional requirements, replace ``all`` with a comma-separated list of package extras.
   The names of these extras can be found in :file:`setup.py`.

Afterwards, copy the systemd_ unit files found in ``/opt/autosuspend/lib/systemd/system/`` to ``/etc/systemd`` and adapt the contained paths to the installation location.
