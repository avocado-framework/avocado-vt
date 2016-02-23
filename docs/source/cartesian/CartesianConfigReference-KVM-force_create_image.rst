
force\_create\_image
====================

Description
-----------

Configures if we want to create an image file during pre processing,
**even if it already exists**. To create an image file only if it **does
not** exist, use `create\_image <CartesianConfigReference-KVM-create_image.html>`_ instead.

To create an image file **even if it already exists**:

::

    force_create_image = yes

Defined On
----------

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
-  `check\_image <CartesianConfigReference-KVM-check_image.html>`_
-  `remove\_image <CartesianConfigReference-KVM-remove_image.html>`_

