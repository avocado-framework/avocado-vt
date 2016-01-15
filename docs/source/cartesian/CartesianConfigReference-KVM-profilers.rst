
profilers
=========

Description
-----------

Sets the list of Autotest profilers to be enabled during the test run
(they're removed from the job's list of profilers when the test
finishes).

This is commonly used to enable the
`kvm\_stat <https://github.com/autotest/autotest/blob/master/client/profilers/kvm_stat/kvm_stat.py>`_
profiler:

::

    profilers = kvm_stat

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_

Used By
-------

-  `client/virt/virt\_utils.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_utils.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

See Also
--------

-  `Setting up profiling on virt-test <../../Profiling>`_
-  `Using and developing job profilers <../../../AddingProfiler>`_

