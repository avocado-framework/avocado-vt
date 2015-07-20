
image\_raw\_device
==================

Description
-----------

Flags whether the backing image for a given drive is a block device
instead of a regular file.

By default we assume all images are backed by files:

::

    image_raw_device = no

But suppose you define a new variant, for another guest, that will have
a disk backed by a block device (say, an LVM volume):

::

    CustomGuestLinux:
        image_name = /dev/vg/linux_guest
        image_raw_device = yes

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/tests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_

Referenced By
-------------

-  `How to run virt-test tests on an existing guest
   image? <../../RunTestsExistingGuest>`_

