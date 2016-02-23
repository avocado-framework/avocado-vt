
kill\_vm\_gracefully
====================

Description
-----------

Flags whether a graceful shutdown command should be sent to the VM guest
OS before attempting to either halt the VM at the hypervisor side
(sending an appropriate command to QEMU or even killing its process).

Of course, this is only valid when `kill\_vm <CartesianConfigReference-KVM-kill_vm.html>`_
is set to 'yes'.

To force killing VMs without using a graceful shutdown command (such as
'shutdown -h now'):

::

    kill_vm_gracefully = no

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/guest-os.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/guest-os.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_
-  `client/tests/kvm/unittests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/unittests.cfg.sample>`_

Used By
-------

-  `client/virt/virt\_env\_process.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_env_process.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See also
--------

-  `kill\_vm <CartesianConfigReference-KVM-kill_vm.html>`_
-  `kill\_vm\_timeout <CartesianConfigReference-KVM-kill_vm_timeout.html>`_
-  `kill\_unresponsive\_vms <CartesianConfigReference-KVM-kill_unresponsive_vms.html>`_

