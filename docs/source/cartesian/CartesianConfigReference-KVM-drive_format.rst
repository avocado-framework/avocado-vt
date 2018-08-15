
drive\_format
=============

Description
-----------

Sets the format for a given drive.

Usually this passed directly to qemu 'if' sub-option of '-drive' command
line option. But in some special cases, such as when drive\_format is
set to 'ahci' or 'usb2', some special magic happens (see
`client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
for more information).

Currently available options in qemu include: ide, scsi, sd, mtd, floppy,
pflash, virtio.

Currently used options in Avocado-VT are: ide, scsi, virtio, ahci,
usb2.

Example:

::

    drive_format = ide

Defined On
----------

-  `shared/cfg/guest-hw.cfg <https://github.com/avocado-framework/avocado-vt/blob/master/shared/cfg/guest-hw.cfg>`_

Used By
-------

-  `virttest/qemu\_vm.py <https://github.com/avocado-framework/avocado-vt/blob/master/virttest/qemu_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

