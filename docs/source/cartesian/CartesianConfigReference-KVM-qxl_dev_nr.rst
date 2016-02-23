
qxl\_dev\_nr
============

Description
-----------

Sets the number of display devices available through
`SPICE <http://spice-space.org/faq>`_. This is only valid when
`qxl <CartesianConfigReference-KVM-qxl.html>`_ is set.

The default configuration enables a single display device:

::

    qxl_dev_nr = 1

Note that due to a limitation in the current Autotest code (see
`client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_)
this setting is only applied when the QEMU syntax is:

::

    # qemu -qxl 2

and not applied when the syntax is:

::

    # qemu -vga qxl

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
-  vga?
-  `display <CartesianConfigReference-KVM-display.html>`_

