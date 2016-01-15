
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

-  `images <images>`_
-  `image\_name <image_name>`_
-  `image\_format <image_format>`_
-  `create\_image <create_image>`_
-  `force\_create\_image <force_create_image>`_

