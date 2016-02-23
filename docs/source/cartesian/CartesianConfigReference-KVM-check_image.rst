
check\_image
============

Description
-----------

Configures if we want to run a check on the image files during post
processing. A check usually means running 'qemu-img info' and 'qemu-img
check'.

This is currently only enabled when `image\_format <CartesianConfigReference-KVM-image_format.html>`_
is set to 'qcow2'.

::

    variants:
        - @qcow2:
            image_format = qcow2
            check_image = yes

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_

Used By
-------

-  `client/virt/virt\_env\_process.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_env_process.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `images <CartesianConfigReference-KVM-images.html>`_
-  `image\_name <CartesianConfigReference-KVM-image_name.html>`_
-  `image\_format <CartesianConfigReference-KVM-image_format.html>`_
-  `create\_image <CartesianConfigReference-KVM-create_image.html>`_
-  `remove\_image <CartesianConfigReference-KVM-remove_image.html>`_

