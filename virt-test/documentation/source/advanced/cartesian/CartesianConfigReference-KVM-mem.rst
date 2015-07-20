
mem
===

Description
-----------

Sets the amount of memory (in MB) a VM will have.

The amount of memory a VM will have for most tests is of the main VM is
1024:

::

    mem = 1024

But for running KVM unittests, we currently set that to 512:

::

    mem = 512

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

