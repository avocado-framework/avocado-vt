
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
5000-5899, and all traffic to/from this port will be redirect to guest's
port 22.

Defined On
----------

-  `shared/cfg/base.cfg <https://github.com/avocado-framework/avocado-vt/blob/master/shared/cfg/base.cfg>`_

Used By
-------

-  `virttest/qemu\_vm.py <https://github.com/avocado-framework/avocado-vt/blob/master/virttest/qemu_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See also
--------

-  `guest\_port <CartesianConfigReference-KVM-guest_port.html>`_
-  `guest\_port\_remote\_shell <CartesianConfigReference-KVM-guest_port_remote_shell.html>`_

