
bridge
======

Description
-----------

Sets the name of the bridge to which a VM nic will be added to. This
only applies to scenarios where 'nic\_mode' is set to 'tap'.

It can be set as a default to all nics:

::

    bridge = virbr0

Or to a specific nic, by prefixing the parameter key with the nic name,
that is for attaching 'nic1' to bridge 'virbr1':

::

    bridge_nic1 = virbr1

Defined On
----------

-  `client/tests/kvm/tests\_base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests_base.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
-  `client/virt/virt\_utils.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_utils.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

