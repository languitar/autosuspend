.. _external-command-activity-scripts:

External command scripts for activity detection
###############################################

A collection of user-provided scripts to use with the :ref:`check-external-command` check for activity detection.

pyLoad
******

`pyLoad <https://pyload.net/>`__ uses an uncommon login theme for its API and hence two separate requests are required to query for active downloads.
Use something along the following lines to query pyLoad.

.. code-block:: bash

   #!/bin/bash

   SessionID=$(curl -s "http://127.0.0.1:8000/api/login" -g -H "Host: 127.0.0.1:8000" -H "Content-Type: application/x-www-form-urlencoded" --data "username=user&password=password" | jq -r)

   SessionStatus=$(curl -s  "http://127.0.0.1:8000/api/statusServer" -g -H "Host: 127.0.0.1:8000" -H "Content-Type: application/x-www-form-urlencoded" --data "session=$SessionID" | jq -r '.active')

   if [ $SessionStatus -eq 1 ]
   then
     exit 0
   else
     exit 1
   fi

Source: :issue:`102`
