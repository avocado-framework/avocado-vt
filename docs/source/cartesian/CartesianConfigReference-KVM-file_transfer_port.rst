
file\_transfer\_port
====================

Description
-----------

Sets the port on which the application used to transfer files to and
from the guest will be listening on.

When `file\_transfer\_client <file_transfer_client>`_ is scp, this
is by default 22:

::

    variants:
        - @Linux:
            file_transfer_client = scp
            file_transfer_port = 22

And for rss, the default is port 10023:

::

    variants:
        - @Windows:
            file_transfer_client = rss
            file_transfer_port = 10023:

Defined On
----------

-  `client/tests/kvm/guest-os.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/guest-os.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `redirs <redirs>`_
-  `file\_transfer\_client <file_transfer_client>`_
-  `guest\_port\_file\_transfer <guest_port_file_transfer>`_

