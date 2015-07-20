
keep\_screendumps
=================

Description
-----------

Flags whether screendumps (screenshots of the VM console) should be kept
or delete during post processing.

To keep the screendumps:

::

    keep_screendumps = yes

Usually we're only interested in keeping screendumps on situations with
failures, to ease the debugging:

::

    keep_screendumps_on_error = yes

Defined On
----------

The stock configuration key (without suffix) is not currently defined on
any sample cartesian configuration file.

The configuration key with the 'on\_error' suffix is defined on:

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_

Used By
-------

-  `client/virt/virt\_env\_process.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_env_process.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

