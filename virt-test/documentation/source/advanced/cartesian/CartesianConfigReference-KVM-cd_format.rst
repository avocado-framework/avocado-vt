
cd\_format
==========

Description
-----------

Sets the format for a given cdrom drive. This directive exists to do
some special magic for cd drive formats 'ahci' and 'usb2' (see
`client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
for more information).

Currently used options in virt-test are: ahci and usb2.

Example:

::

    variants:
        - usb.cdrom:
            cd_format = usb2

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See also
--------

-  `drive\_format <drive_format>`_

