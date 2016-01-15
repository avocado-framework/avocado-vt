
drive\_cache
============

Description
-----------

Sets the caching mode a given drive. Currently the valid values are:
writethrough, writeback, none and unsafe.

Example:

::

    drive_cache = writeback

This option can also be set specifically to a drive:

::

    drive_cache_cd1 = none

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

