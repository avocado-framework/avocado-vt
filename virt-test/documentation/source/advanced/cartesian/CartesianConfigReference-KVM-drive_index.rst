
drive\_index
============

Description
-----------

Sets the index, that is, ordering precedence of a given drive. Valid
values are integers starting with 0.

Example:

::

    drive_index_image1 = 0
    drive_index_cd1 = 1

This will make the drive that has 'image1' appear before the drive that
has 'cd1'.

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/guest-os.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/guest-os.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_
-  `client/tests/kvm/virtio-win.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/virtio-win.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

