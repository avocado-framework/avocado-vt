
image\_name
===========

Description
-----------

Sets the name of an image file.

If the image file is not a block device (see
`image\_raw\_device <CartesianConfigReference-KVM-image_raw_device.html>`_)
the actual file created will be named accordingly (together with the extension,
according to `image\_format <CartesianConfigReference-KVM-image_format.html>`_).

When this configuration key is used without a suffix, it's setting the
name of all images without a specific name. The net effect is that it
sets the name of the 'default' image. Example:

::

    # Guests
    variants:
        - @Linux:
            variants:
                - Fedora:
                    variants:
                        - 15.64:
                            image_name = f15-64

This example means that when a Fedora 15 64 bits is installed, and has a
backing image file created, it's going to be named starting with
'f15-64'. If the `image\_format <CartesianConfigReference-KVM-image_format.html>`_
specified is 'qcow2', then the complete filename will be 'f15-64.qcow2'.

When this configuration key is used with a suffix, it sets the name of a
specific image. Example:

::

    # Tests
    variants:
        - block_hotplug: install setup image_copy unattended_install.cdrom
            images += " stg"
            image_name_stg = storage

Defined On
----------

-  `client/tests/kvm/guest-os.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/guest-os.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_
-  `client/tests/kvm/tests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
-  `client/tests/kvm/tests/qemu\_img.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/qemu_img.py>`_

Referenced By
-------------

-  `How to run virt-test tests on an existing guest
   image? <../../RunTestsExistingGuest>`_

See Also
--------

-  `images <CartesianConfigReference-KVM-images.html>`_
-  `image\_format <CartesianConfigReference-KVM-image_format.html>`_
-  `image\_raw\_device <CartesianConfigReference-KVM-image_raw_device.html>`_

