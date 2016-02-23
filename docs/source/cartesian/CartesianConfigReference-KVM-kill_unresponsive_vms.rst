
kill\_unresponsive\_vms
=======================

Description
-----------

Configures whether VMs that are running, but do not have a responsive
session (for example via SSH), should be destroyed (of course, not
`gracefully <kill_vm_gracefully>`_) during post processing.

This behavior is enabled by default. To turn it off and leave
unresponsive VMs lying around (usually **not** recommended):

::

    kill_unresponsive_vms = no

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_

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
-  `kill\_vm\_gracefully <CartesianConfigReference-KVM-kill_vm_gracefully.html>`_

