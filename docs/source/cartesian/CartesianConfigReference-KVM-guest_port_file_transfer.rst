
guest\_port\_file\_tranfer
==========================

Description
-----------

Sets the port of the server application running inside guests that will
be used for transferring files to and from this guest.

On Linux VMs, the `file\_transfer\_client <file_transfer_client>`_
is set by default to 'scp', and this the port is set by default to the
standard SSH port (22).

For Windows guests, the
`file\_transfer\_client <file_transfer_client>`_ is set by default
to 'rss', and the port is set by default to 10023.

This is a specialization of the `guest\_port <guest_port>`_
configuration entry.

Example, default entry:

::

    guest_port_file_transfer = 22

Overridden on Windows variants:

::

    variants:
        - @Windows:
            guest_port_file_transfer = 10023

Defined On
----------

-  `client/tests/kvm/guest-os.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/guest-os.cfg.sample>`_

Used By
-------

-  `client/virt/kvm\_vm.py <https://github.com/autotest/autotest/blob/master/client/virt/kvm_vm.py>`_
-  `client/virt/virt\_utils.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_utils.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `redirs <redirs>`_
-  `file\_transfer\_port <file_transfer_port>`_
-  `file\_transfer\_client <file_transfer_client>`_

