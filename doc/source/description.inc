|project_program| is a daemon that periodically suspends a system on inactivity and wakes it up again automatically in case it is needed.
For this purpose, |project_program| periodically iterates a number of user-configurable activity checks, which indicate whether an activity on the host is currently present that should prevent the host from suspending.
In case one of the checks indicates such activity, no action is taken and periodic checking continues.
Otherwise, in case no activity can be detected, this state needs to be present for a specified amount of time before the host is suspended by |project_program|.
In addition to the activity checks, wake up checks are used to determine planned future activities of the system (for instance, a TV recording or a periodic backup).
In case such activities are known before suspending, |project_program| triggers a command to wake up the system automatically before the soonest activity.
