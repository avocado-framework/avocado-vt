
kill\_vm\_timeout
=================

Description
-----------

Configures the amount of time, in seconds, to wait for VM shutdown
during the post processing.

This is only relevant if `kill\_vm <CartesianConfigReference-KVM-kill_vm.html>`_ is
actually set to 'yes'.

To set the timeout to one minute:

::

    kill_vm_timeout = 60

Defined On
----------

-  `client/tests/kvm/guest-os.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/guest-os.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_

Used By
-------

-  `client/virt/virt\_env\_process.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_env_process.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See also
--------

-  `kill\_vm <CartesianConfigReference-KVM-kill_vm.html>`_
-  `kill\_vm\_gracefully <CartesianConfigReference-KVM-kill_vm_gracefully.html>`_
-  `kill\_unresponsive\_vms <CartesianConfigReference-KVM-kill_unresponsive_vms.html>`_

