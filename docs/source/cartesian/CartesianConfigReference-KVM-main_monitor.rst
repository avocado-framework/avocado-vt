
main\_monitor
=============

Description
-----------

Sets the default monitor for a VM, meaning that when a test accesses the
**monitor** property of a **VM** class instance, that one monitor will
be returned.

Usually a VM will have a single monitor, and that will be a regular
Human monitor:

::

    main_monitor = humanmonitor1

If a **main\_monitor** is not defined, the **monitor** property of a
**VM** class instance will assume that the first monitor set in the
`monitors <CartesianConfigReference-KVM-monitors.html>`_ list is the main monitor.

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/unittests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/unittests.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `monitors <CartesianConfigReference-KVM-monitors.html>`_
-  `monitor\_type <CartesianConfigReference-KVM-monitor_type.html>`_
-  `client/virt/kvm\_monitor.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_monitor.py>`_

