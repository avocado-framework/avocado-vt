
monitors
========

Description
-----------

Sets the list of
`monitors <http://qemu.weilnetz.de/qemu-doc#pcsys_005fmonitor>`_
that a VM currently has running. See [ QEMU has two types of monitors:

-  The regular, also known as Human monitor, intended for interaction
   with people (but also very much used by other tools, Autotest
   inclusive)
-  The QMP monitor, a monitor that speaks the
   `QMP <http://wiki.qemu.org/QMP>`_ protocol.

Usually a VM will have a single monitor, and that will be a regular
Human monitor:

::

    monitors = humanmonitor1
    main_monitor = humanmonitor1
    monitor_type_humanmonitor1 = human
    monitor_type = human

The monitor type is defined by `monitor\_type <monitor_type>`_.

Here's a more detailed exaplanation of the configuration snippet above:

::

    monitors = humanmonitor1

The default VM will have only one monitor, named **humanmonitor1**.

::

    main_monitor = humanmonitor1

The main monitor will also be **humanmonitor1**. When a test has to talk
to a monitor, it usually does so through the main monitor.

::

    monitor_type_humanmonitor1 = human

This configuration sets the specific type of the **humanmonitor1** to be
**human**.

::

    monitor_type = human

And finally this configuration sets the default monitor type also to be
**human**.

Suppose you define a new monitor for your VMs:

::

    monitors += ' monitor2'

Unless you also define:

::

    monitor_type_monitor2 = qmp

**monitor2** will also be a human monitor.

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/unittests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/unittests.cfg.sample>`_

Used By
-------

-  `client/tests/kvm/kvm.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/kvm.py>`_
-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
-  `client/virt/virt\_test\_utils.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_test_utils.py>`_

Note: most tests that interact with the monitor do so through the
**monitor** property of the **VM** class, and not by evaluating this
parameter value. This is usally only done by the **VM** class.

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `client/virt/kvm\_monitor.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_monitor.py>`_

