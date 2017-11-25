|project_program| is a daemon that periodically that suspends a system on inactivity.
For this purpose, it periodically iterates a number of user-configurable checks, which shall indicate whether a certain activity on the host is currently present that should prevent the host from suspending.
In case one of the checks indicates such activity, no action is taken and periodic checking continues.
Otherwise, in case no activity can be detected, this state needs to be present for a specified amount of time before the host is suspended by |project_program|.
