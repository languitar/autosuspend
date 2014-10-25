autosuspend
===========

Autosuspend is a python daemon that suspends a system if certain conditions are met, or not met.

Requirements
============
python3 with the following modules:  os, sys, configparser, logging,  psutil,  subprocess,  time,  threading,  logging, http.server

Features
========
It can currently check the following conditions:

SSH:
    by matching user
        any username that matches a given list blocks suspend
    by matching host
        any hostname that matches a given list blocks suspend

SAMBA:
    any active Samba connection will block suspend.
        Since this uses the output of smbstatus it (or the package that contains) it must be installed. Also it parses the output of smbstatus. 
        If your smbstatus output doesn't use a ---- to divide the heading from list of connections it will fail

LOAD:
    if the current systemload is greater than a given value suspend will be blocked.
        NOTICE: Change the load according to your system. For example: A load of 2.7 is very high for a single cpu system, while it is light load for a quad-cpu system.

PING:
    if one of the hosts respond to a ICMP request suspend will be blocked

PROCESSES:
    if currently running processes match the suspend will be blocked.
        You might use this to hinder the system from suspending when for example your rsync runs

WEBSERVER:
    if a http connection is made to the port the system will suspend immediately
        This is a way to directly initiate a suspend. If you open the port in a webbrowser the suspend will be initiated immediately.
        For safety reasons you should set a password. This might not be secure, but will make it harder to suspend the system by accident. 
        you can disable the password by leaving it empty.
        The suspending by webserver is not checking for the other conditions to apply. it will suspend instantly

Example configuration file
===========
The following options should be put in /etc/autosuspend.conf

[autosuspend]
interval=600
debug=true
ping=true
pinghosts=client,raspberrypi
ssh=true
sshusers=user,user2
sshhosts=client2,raspberrypi
webhost=true
webport=4567
webpass=password
smb=true
loadthreshold=1.5
processes=rsync,clamav
suspend_cmd = /bin/echo
logfile = /var/log/autosuspend.log
