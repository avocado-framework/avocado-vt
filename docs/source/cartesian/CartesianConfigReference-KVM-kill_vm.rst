
kill\_vm
========

Description
-----------

Configures whether a VM should be shutdown during post processing. How
exactly the VM will be shutdown is configured by other parameters such
as `kill\_vm\_gracefully <CartesianConfigReference-KVM-kill_vm_gracefully.html>`_
and `kill\_vm\_timeout <CartesianConfigReference-KVM-kill_vm_timeout.html>`_.

To force shutdown during post processing:

::

    kill_vm = yes

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

-  `kill\_vm\_timeout <CartesianConfigReference-KVM-kill_vm_timeout.html>`_
-  `kill\_vm\_gracefully <CartesianConfigReference-KVM-kill_vm_gracefully.html>`_
-  `kill\_unresponsive\_vms <CartesianConfigReference-KVM-kill_unresponsive_vms.html>`_

