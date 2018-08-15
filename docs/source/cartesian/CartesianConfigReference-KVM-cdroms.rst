
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

-  `shared/cfg/base.cfg <https://github.com/avocado-framework/avocado-vt/blob/master/shared/cfg/base.cfg>`_
-  `shared/cfg/virtio-win.cfg <https://github.com/avocado-framework/avocado-vt/blob/master/shared/cfg/virtio-win.cfg>`_

Used By
-------

-  `virttest/qemu\_vm.py <https://github.com/avocado-framework/avocado-vt/blob/master/virttest/qemu_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

