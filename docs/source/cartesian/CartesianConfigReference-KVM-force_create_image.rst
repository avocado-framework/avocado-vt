
force\_create\_image
====================

Description
-----------

Configures if we want to create an image file during pre processing,
**even if it already exists**. To create an image file only if it **does
not** exist, use `create\_image <create_image>`_ instead.

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

-  `images <images>`_
-  `image\_name <image_name>`_
-  `image\_format <image_format>`_
-  `create\_image <create_image>`_
-  `check\_image <check_image>`_
-  `remove\_image <remove_image>`_

