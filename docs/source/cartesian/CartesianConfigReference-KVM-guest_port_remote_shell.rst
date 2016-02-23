
guest\_port\_remote\_shell
==========================

Description
-----------

Sets the port of the remote shell server that runs inside guests. On
Linux VMs, this is the set by default to the standard SSH port (22), and
for Windows guests, set by default to port 10022.

This is a specialization of the `guest\_port <guest_port>`_
configuration entry.

Example, default entry:

::

    guest_port_remote_shell = 22

Overridden on Windows variants:

::

    variants:
        - @Windows:
            guest_port_remote_shell = 10022

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/guest-os.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/guest-os.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
-  `client/virt/virt\_utils.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_utils.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `redirs <CartesianConfigReference-KVM-redirs.html>`_
-  shell\_port?

