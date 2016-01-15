
main\_vm
========

Description
-----------

Sets name of the main VM.

There's nothing special about this configuration item, except that most
tests will also reference its value when fetching a VM from the
Environment (see class **Env** on file
`client/virt/virt\_utils.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_utils.py>`_).

The default name of the main VM is **vm1**:

::

    main_vm = vm1

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/unittests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/unittests.cfg.sample>`_

Referenced By
-------------

No other documentation currently references this configuration key.

