
monitor\_type
=============

Description
-----------

Sets the type of the
`monitor <http://qemu.weilnetz.de/qemu-doc#pcsys_005fmonitor>`_.
QEMU has two types of monitors:

-  The regular, also known as Human monitor, intended for interaction
   with people (but also very much used by other tools, Autotest
   inclusive)
-  The QMP monitor, a monitor that speaks the
   `QMP <http://wiki.qemu.org/QMP>`_ protocol.

To set the default monitor type to be a
`QMP <http://wiki.qemu.org/QMP>`_ monitor:

::

    monitor_type = qmp

To set the type of a specific monitor use:

::

    monitor_type_humanmonitor1 = human

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

-  `client/virt/kvm\_monitor.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_monitor.py>`_

