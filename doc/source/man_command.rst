:orphan:

.. _man-command:

|project|
#########

Synopsis
********

|project_bold| [*options*] **daemon|presuspend** [*subcommand options*]

Description
***********

.. include:: description.inc

If not specified via a command line argument, |project_program| looks for a default configuration at :file:`/etc/autosuspend.conf`.
:manpage:`autosuspend.conf(5)` describes the configuration file, the available checks, and their configuration options.

Options
*******

.. toctree::

   options

Bugs
****

Please report bugs at the project repository at https://github.com/languitar/autosuspend.

See also
********

:manpage:`autosuspend.conf(5)`, online documentation including FAQs at https://autosuspend.readthedocs.io/
