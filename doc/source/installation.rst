.. _installation:

Installation instructions
#########################

|project_program| is designed for Python **3** and does not work with Python 2.

.. note::

   After installation, do not forget to enable and start |project| vis `systemd`_ as described in :ref:`systemd-integration`.

Requirements
************

The minimal requirements are.

* `Python 3`_ >= 3.7
* `psutil`_
* `portalocker`_

Additionally, the some checks need further dependencies to function properly.
Please refer to :ref:`available-checks` for individual requirements.

If checks using URLs to load data should support ``file://`` URLs, `requests-file`_ is needed.

Binary packages
***************

Debian
======

Installation from official package sources::

    apt-get install autosuspend

Archlinux (AUR)
~~~~~~~~~~~~~~~

|project| is available as an `Archlinux AUR package <https://aur.archlinux.org/packages/autosuspend/>`_.

Installation via :program:`aurman`::

    aurman -S autosuspend

Other `AUR helpers <https://wiki.archlinux.org/index.php/AUR_helpers>`_ may be used, too.

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

From-source installation
************************

|project_program| provides a usual :file:`setup.py` file for installation using common `setuptools`_ methods.
Briefly, the following steps are necessary to install |project_program|:

.. code-block:: bash

   git clone https://github.com/languitar/autosuspend.git
   cd autosuspend
   python3 setup.py install # with desired options

To build the documentation, the following command can be used:

.. code-block:: bash

   python3 setup.py build_sphinx
