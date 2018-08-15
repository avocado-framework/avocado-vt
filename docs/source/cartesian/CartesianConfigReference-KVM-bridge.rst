
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

-  `shared/cfg/guest-hw.cfg <https://github.com/avocado-framework/avocado-vt/blob/master/shared/cfg/guest-hw.cfg>`_
-  `shared/cfg/machines.cfg <https://github.com/avocado-framework/avocado-vt/blob/master/shared/cfg/machines.cfg>`_

Used By
-------

-  `virttest/qemu\_vm.py <https://github.com/avocado-framework/avocado-vt/blob/master/virttest/qemu_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

