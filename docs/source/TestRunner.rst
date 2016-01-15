==========================
Avocado VT - Running Tests
==========================

This doc assumes you already read the introductory GetStarted documentation.
This extra doc is just to teach you some useful tricks when using the runner.

Getting Help
============

The best way to get help from the command line options is the --help flag.
The man page is also very helpful.

::

    $ avocado --help
    $ man avocado


General Flow
============

Avocado-VT basically will:

1) Get a dict with test parameters
2) Based on these params, prepare the environment - create or destroy vm
   instances, create/check disk images, among others
3) Execute the test itself, that will use several of the params defined to
   carry on with its operations, that usually involve:
4) If a test did not raise an exception, it PASSed
5) If a test raised a TestFail exception, it FAILed. Otherwise, it ERRORed.
6) Based on what happened during the test, perform cleanup actions, such as
   killing vms, and remove unused disk images.

The list of parameters is obtained by parsing a set of configuration files
The command line options usually modify even further the parser file, so
we can introduce new data in the config set.

Common Operations -- Listing guests
===================================

If you want to see all guests defined, you can use

::

    avocado list -vt-type [test type] --list-guests


This will generate a list of possible guests that can be used for tests,
provided that you have an image with them. The list will show which guests
don't have an image currently available. If you did perform the usual
bootstrap procedure, only JeOS.17.64 will be available.

Now, let's assume you have the image for another guest. Let's say you've
installed Fedora 17, 64 bits, and that --list-guests shows it as downloaded

::

    avocado list --vt-type qemu --vt-list-guests
    ...
    Linux.CentOS.6.6.i386.i440fx (missing centos66-32.qcow2)
    Linux.CentOS.6.6.x86_64.i440fx (missing centos66-64.qcow2)

You can list all the available tests for Fedora.17.64 (you must use the exact
string printed by the test, minus obviously the index number, that's there
only for informational purposes:

::

    avocado list --vt-type qemu --vt-guest-os Linux.CentOS.6.6.i386.i440fx --verbose
    ...
    VT           io-github-autotest-qemu.trans_hugepage.base
    VT           io-github-autotest-qemu.trans_hugepage.defrag
    VT           io-github-autotest-qemu.trans_hugepage.swapping
    VT           io-github-autotest-qemu.trans_hugepage.relocated
    VT           io-github-autotest-qemu.trans_hugepage.migration
    VT           io-github-autotest-qemu.trans_hugepage.memory_stress
    VT           io-github-autotest-qemu.ntpd
    VT           io-github-autotest-qemu.clock_getres
    VT           io-github-autotest-qemu.autotest_regression
    VT           io-github-autotest-qemu.shutdown

    ACCESS_DENIED: 0
    BROKEN_SYMLINK: 0
    BUGGY: 0
    FILTERED: 0
    INSTRUMENTED: 52
    MISSING: 0
    NOT_A_TEST: 27
    SIMPLE: 3
    VT: 2375

Then you can execute one in particular. It's the same idea, just copy the
individual test you want and run it:

::

    avocado run balloon_check --vt-type qemu --vt-guest-os Fedora.21

And it'll run that particular test.
