
spice
=====

Description
-----------

Sets extra arguments to be passed to the QEMU **-spice** command line
argument.

Note that there's no need to pass a port number, as this will be
automatically allocated from the 8000 - 8100 range.

By default, the extra arguments disable authentication:

::

    spice = disable-ticketing

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

-  `qxl <CartesianConfigReference-KVM-qxl.html>`_
-  `qxl\_dev\_nr <CartesianConfigReference-KVM-qxl_dev_nr.html>`_
-  vga?
-  `display <CartesianConfigReference-KVM-display.html>`_

