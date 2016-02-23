
guest\_port\_unattended\_install
================================

Description
-----------

Sets the port of the helper application/script running inside guests
that will be used for flagging the end of the unattended install.

Both on Linux and Windows VMs, the default value is 12323:

::

    guest_port_unattended_install = 12323

This must match with the port number on unattended install files. On
Linux VMs, this is hardcoded on kickstart files '%post' section:

::

    %post --interpreter /usr/bin/python
    ...
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('', 12323))
    server.listen(1)
    (client, addr) = server.accept()
    client.send("done")
    client.close()

This is a specialization of the `guest\_port <guest_port>`_
configuration entry.

Defined On
----------

-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_

Used By
-------

-  `client/tests/kvm/tests/unattended\_install.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/unattended_install.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `redirs <CartesianConfigReference-KVM-redirs.html>`_

