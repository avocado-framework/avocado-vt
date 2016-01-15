
check\_image
============

Description
-----------

Configures if we want to run a check on the image files during post
processing. A check usually means running 'qemu-img info' and 'qemu-img
check'.

This is currently only enabled when `image\_format <image_format>`_
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

-  `images <images>`_
-  `image\_name <image_name>`_
-  `image\_format <image_format>`_
-  `create\_image <create_image>`_
-  `remove\_image <remove_image>`_

