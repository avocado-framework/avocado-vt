
images\_good
============

Description
-----------

Sets the URI of a NFS server that hosts "good" (think "golden") images,
that will be copied to the local system prior to running other tests.

The act of copying of "good" images is an alternative to installing a VM
from scratch before running other tests.

The default value is actually an invalid value that must be changed if
you intend to use this feature:

::

    images_good = 0.0.0.0:/autotest/images_good

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_

Used By
-------

-  `client/virt/tests/image\_copy.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/image_copy.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

