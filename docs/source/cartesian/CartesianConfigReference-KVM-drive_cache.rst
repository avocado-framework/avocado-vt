
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

-  `shared/cfg/base.cfg <https://github.com/avocado-framework/avocado-vt/blob/master/shared/cfg/base.cfg>`_

Used By
-------

-  `virttest/qemu\_vm.py <https://github.com/avocado-framework/avocado-vt/blob/master/virttest/qemu_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

