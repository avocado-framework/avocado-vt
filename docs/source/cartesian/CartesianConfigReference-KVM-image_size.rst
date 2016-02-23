
image\_size
===========

Description
-----------

Sets the size of image files. This applies to images creation and also
validation tests (when checking that a image was properly created
according to what was requested).

By default the image size is set to 10G:

::

    image_size = 10G

But a VM can have other drives, backed by other image files (or block
devices), with different sizes:

::

    # Tests
    variants:
        - block_hotplug: install setup image_copy unattended_install.cdrom
            images += " stg"
            boot_drive_stg = no
            image_name_stg = storage
            image_size_stg = 1G

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/guest-os.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/guest-os.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_
-  `client/tests/kvm/tests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
-  `client/tests/kvm/tests/qemu\_img.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/qemu_img.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `images <CartesianConfigReference-KVM-images.html>`_
-  `image\_name <CartesianConfigReference-KVM-image_name.html>`_
-  `image\_format <CartesianConfigReference-KVM-image_format.html>`_

