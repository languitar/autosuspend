Frequently Asked Questions
##########################

Usage
*****

How do I add custom checks?
===========================

Two options:

* Use a script with the ``ExternalCommand`` check.

* Implement a Python module with you check being a subclass of
  :class:`autosuspend.checks.Activity` or
  :class:`autosuspend.checks.Wakeup` and install it alongside |project|.
  The custom check class can then be referenced in the config with its full dotted path, for instance, ``mymodule.MyCheck``, in the `class` field.

Error messages
**************

No connection adapters were found for '\file://\*'
==================================================

You need to install the `requests-file`_ package for ``file://`` URIs to work.
