
drive\_werror
=============

Description
-----------

Sets the behavior for the VM when a drive encounters a read or write
error. This is passed to QEMU 'werror' sub-option of the '-drive'
command line option.

Valid for QEMU are: ignore, stop, report, enospc.

Example:

::

    drive_werror = stop

Defined On
----------

-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

