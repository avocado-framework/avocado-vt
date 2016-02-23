
remove\_image
=============

Description
-----------

Configures if we want to remove image files during post processing.

To keep all images after running tests:

::

    remove_image = no

On a test with multiple transient images, to remove all but the main
image (**image1**), use:

::

    remove_image = yes
    remove_image_image1 = no

Defined On
----------

-  `client/tests/kvm/tests\_base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests_base.cfg.sample>`_

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
-  `force\_create\_image <CartesianConfigReference-KVM-force_create_image.html>`_

