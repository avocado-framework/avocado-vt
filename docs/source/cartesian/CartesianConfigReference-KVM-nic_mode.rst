
nic\_mode
=========

Description
-----------

Configures the mode of a Network Interface Card.

Suitable values for this configuration item are either **user** or
**tap**.

`User
mode <http://wiki.qemu.org/Documentation/Networking#User_Networking_.28SLIRP.29>`_
networking is the default **on QEMU**, but `Tap
mode <http://wiki.qemu.org/Documentation/Networking#Tap>`_ is the
current default in Autotest:

::

    nic_mode = tap

When **nic\_mode** is set to
`Tap <http://wiki.qemu.org/Documentation/Networking#Tap>`_ you should
also set a `bridge <CartesianConfigReference-KVM-bridge.html>`_.

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_
-  `client/tests/kvm/migration\_control.srv <https://github.com/autotest/autotest/blob/master/client/tests/kvm/migration_control.srv>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
-  `client/tests/kvm/tests/physical\_resources\_check.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/physical_resources_check.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `bridge <CartesianConfigReference-KVM-bridge.html>`_
-  `redirs <CartesianConfigReference-KVM-redirs.html>`_

