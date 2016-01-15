
create\_image
=============

Description
-----------

Configures if we want to create an image file during pre processing, if
it does **not** already exists. To force the creation of the image file
even if it already exists, use
`force\_create\_image <force_create_image>`_.

To create an image file if it does **not** already exists:

::

    create_image = yes

Defined On
----------

-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_

Used By
-------

-  `client/tests/kvm/tests/qemu\_img.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/qemu_img.py>`_
-  `client/virt/virt\_env\_process.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_env_process.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `images <images>`_
-  `image\_name <image_name>`_
-  `image\_format <image_format>`_
-  `create\_image <create_image>`_
-  `force\_create\_image <force_create_image>`_
-  `remove\_image <remove_image>`_

