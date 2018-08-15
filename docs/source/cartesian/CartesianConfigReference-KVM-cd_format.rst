
cd\_format
==========

Description
-----------

Sets the format for a given cdrom drive. This directive exists to do
some special magic for cd drive formats 'ahci' and 'usb2' (see
`virttest/qemu\_vm.py <https://github.com/avocado-framework/avocado-vt/blob/master/virttest/qemu_vm.py>`_
for more information).

Currently used options in Avocado-VT are: ahci and usb2.

Example:

::

    variants:
        - usb.cdrom:
            cd_format = usb2

Defined On
----------

-  `shared/cfg/virtio-win.cfg <https://github.com/avocado-framework/avocado-vt/blob/master/shared/cfg/virtio-win.cfg>`_
-  `shared/cfg/guest-hw.cfg <https://github.com/avocado-framework/avocado-vt/blob/master/shared/cfg/guest-hw.cfg>`_

Used By
-------

-  `virttest/qemu\_vm.py <https://github.com/avocado-framework/avocado-vt/blob/master/virttest/qemu_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See also
--------

-  `drive\_format <CartesianConfigReference-KVM-drive_format.html>`_

