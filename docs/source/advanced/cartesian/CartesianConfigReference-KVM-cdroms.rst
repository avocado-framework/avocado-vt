
cdroms
======

Description
-----------

Sets the list of cdrom devices that a VM will have.

Usually a VM will start with a single cdrom, named 'cd1'.

::

    cdroms = cd1

But a VM can have other cdroms such as 'unattended' for unattended
installs:

::

    variants:
        - @Linux:
            unattended_install:
                cdroms += " unattended"

And 'winutils' for Microsoft Windows VMs:

::

    variants:
        - @Windows:
            unattended_install.cdrom, whql.support_vm_install:
                cdroms += " winutils"

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/guest-os.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/guest-os.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_
-  `client/tests/kvm/virtio-win.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/virtio-win.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

