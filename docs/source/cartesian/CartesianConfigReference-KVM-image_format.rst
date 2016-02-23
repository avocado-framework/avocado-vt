
image\_format
=============

Description
-----------

Sets the format of the backing image file for a given drive.

The value of this configuration key is usually passed verbatim to image
creation commands. It's worth noticing that QEMU has support for many
formats, while Avocado-VT currently plays really well only with
**qcow2** and **raw**.

You can also use **vmdk**, but it's considered 'not supported', at least
on image conversion tests.

To set the default image format:

::

    image_format = qcow2

To set the image format for another image:

::

    # Tests
    variants:
        - block_hotplug: install setup image_copy unattended_install.cdrom
            images += " stg"
            image_format_stg = raw

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_

Used By
-------

-  `client/virt/virt\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_vm.py>`_
-  `client/tests/kvm/tests/qemu\_img.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/qemu_img.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `images <CartesianConfigReference-KVM-images.html>`_
-  `image\_name <CartesianConfigReference-KVM-image_name.html>`_
-  `image\_size <CartesianConfigReference-KVM-image_size.html>`_

