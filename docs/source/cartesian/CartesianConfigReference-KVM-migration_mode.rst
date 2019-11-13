
migration\_mode
===============

Description
-----------

If migration mode is specified, the VM will be started in incoming mode
for migration. Valid modes for migration are: **tcp**, **unix** and
**exec**.

To start a VM in incoming mode for receiving migration data via tcp:

::

    migration_mode = tcp

A port will be allocated from the range 5200 to 5899.

Defined On
----------

This configuration item is currently not defined on a sample cartesian
configuration file.

Used By
-------

-  `client/tests/kvm/migration\_control.srv <https://github.com/autotest/autotest/blob/master/client/tests/kvm/migration_control.srv>`_

Referenced By
-------------

No other documentation currently references this configuration key.

