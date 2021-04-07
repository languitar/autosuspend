|project| - a daemon to automatically suspend and wake up a system
##################################################################

.. ifconfig:: is_preview

   .. warning::

      This is the documentation for an unreleased preview version of |project|.

.. include:: description.inc

The following diagram visualizes the periodic processing performed by |project|.

.. uml::

   @startuml

   skinparam shadowing false
   skinparam backgroundcolor transparent

   skinparam Padding 8

   skinparam ActivityBackgroundColor #FFFFFF
   skinparam ActivityDiamondBackgroundColor #FFFFFF
   skinparam ActivityBorderColor #333333
   skinparam ActivityDiamondBorderColor #333333
   skinparam ArrowColor #333333

   start

   :Execute activity checks;

   if (Is the system active?) then (no)

     if (Was the system idle before?) then (no)
       :Remember current time as start of system inactivity;
     else (yes)
     endif

     if (Is system idle long enough?) then (yes)

       :Execute wake up checks;

       if (Is a wake up required soon?) then (yes)
         stop
       else
         if (Is any wake up required?) then (yes)
           #BBFFBB:Schedule the earliest wake up;
         else (no)
         endif
       endif

       #BBFFBB:Suspend the system;

     else (no)
       stop
     endif

   else (yes)
     :Forget start of system inactivity;
     stop
   endif

   stop

   @enduml


.. toctree::
   :maxdepth: 2
   :caption: Usage

   installation
   options
   configuration_file
   available_checks
   available_wakeups
   systemd_integration
   external_command_activity_scripts
   api

.. toctree::
   :maxdepth: 2
   :caption: Support

   faq
   debugging
   support
   changelog

Indices and tables
##################

* :ref:`genindex`
* :ref:`search`
