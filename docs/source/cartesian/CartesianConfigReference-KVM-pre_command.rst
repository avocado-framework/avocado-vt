
pre\_command
============

Description
-----------

Configures a command to be executed during pre processing.

The pre processing code will execute the given command, waiting for an
amount of `time <pre_command_timeout>`_ and failing the test unless
the command is considered `noncritical <pre_command_noncritical>`_.

Defined On
----------

This configuration key is not currently defined on any sample cartesian
configuration file in its stock format.

Used By
-------

-  `client/virt/virt\_env\_process.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_env_process.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `pre\_command\_timeout <CartesianConfigReference-KVM-pre_command_timeout.html>`_
-  pre\_command\_non\_critical?

