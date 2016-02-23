
qxl
===

Description
-----------

Flags if the
`VGA <http://qemu.weilnetz.de/qemu-doc#index-g_t_002dvga-54>`_
device should be an of type **qxl**.

The default configuration enables a **qxl** VGA:

::

    qxl = on

Note that if vga? is also set, **qxl** takes precedence over it.

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `qxl\_dev\_nr <CartesianConfigReference-KVM-qxl_dev_nr.html>`_
-  vga?

