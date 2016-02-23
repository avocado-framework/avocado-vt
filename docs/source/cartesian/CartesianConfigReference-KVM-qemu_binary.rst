
qemu\_binary
============

Description
-----------

Sets either the name or full path for the QEMU binary.

By default this is as simple as possible:

::

    qemu_binary = qemu

But while testing the qemu-kvm userspace, one could use:

::

    qemu_binary = /usr/bin/qemu-kvm

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/tests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests.cfg.sample>`_
-  `client/tests/kvm/unittests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/unittests.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
-  `client/virt/virt\_env\_process.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_env_process.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `qemu\_img\_binary <CartesianConfigReference-KVM-qemu_img_binary.html>`_

