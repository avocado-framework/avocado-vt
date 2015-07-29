
redirs
======

Description
-----------

Sets the network redirections between host and guest. These are only
used and necessary when using 'user' mode network.

Example:

::

    redirs = remote_shell
    guest_port_remote_shell = 22

A port will be allocated on the host, usually within the range
5000-6000, and all traffic to/from this port will be redirect to guest's
port 22.

Defined On
----------

-  `client/tests/kvm/tests\_base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests_base.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See also
--------

-  `guest\_port <guest_port>`_
-  `guest\_port\_remote\_shell <guest_port_remote_shell>`_

