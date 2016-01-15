
nics
====

Description
-----------

Sets the list of network interface cards that a VM will have.

Usually a VM will start with a single nic, named nic1:

::

    nics = nic1

But a VM can have other nics. Some tests (usually network related) add
other nics. One obvious example is the
`bonding <http://www.linuxfoundation.org/collaborate/workgroups/networking/bonding>`_
test:

::

    # Tests
    variants:
        - nic_bonding: install setup image_copy unattended_install.cdrom
            nics += ' nic2 nic3 nic4'

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_

Used By
-------

-  `client/virt/virt\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_vm.py>`_
-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
-  `client/tests/kvm/tests/nic\_bonding.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/nic_bonding.py>`_
-  `client/tests/kvm/tests/physical\_resources\_check.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/physical_resources_check.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

