
images
======

Description
-----------

Sets the list of disk devices (backed by a image file or device) that a
VM will have.

Usually a VM will start with a single image, named image1:

::

    images = image1

But a VM can have other images. One example is when we test the maximum
number of disk devices supported on a VM:

::

    # Tests
    variants:
        - multi_disk: install setup image_copy unattended_install.cdrom
            variants:
                - max_disk:
                    images += " stg stg2 stg3 stg4 stg5 stg6 stg7 stg8 stg9 stg10 stg11 stg12 stg13 stg14 stg15 stg16 stg17 stg18 stg19 stg20 stg21 stg22 stg23"

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/guest-os.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/guest-os.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
-  `virt\_env\_process.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_env_process.py>`_
-  `client/tests/kvm/tests/enospc.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/enospc.py>`_
-  `client/tests/kvm/tests/image\_copy.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/image_copy.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

