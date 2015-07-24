================
Virt Test Runner
================

As you probably know, virt tests was derived from a set of tests written
for the autotest testing framework. Therefore, the test suite depended
entirely on autotest for libraries *and* the autotest test harness to
execute the test code.

However, autotest is a large framework, that forced a steep learning curve
for people and a lot of code download (the autotest git repo is quite large
these days, due to more than 6 years of history).

Due to this, virt tests was separated to its own test suite project, that
still can run fine under autotest (in fact, it is what we use to do daily
fully automated testing of KVM and QEMU), but that can be executed separately,
depending only on a handful of autotest libraries.

This doc assumes you already read the introductory GetStarted documentation.
This extra doc is just to teach you some useful tricks when using the runner.

Getting Help
============

The best way to get help from the command line options is the --help flag:

::

    ./run --help


General Flow
============

The test runner is nothing more than a very simple test harness, that replaces
the autotest harness, and a set of options, that will trigger actions to
create a test list and execute it. The way the tests work is:

1) Get a dict with test parameters
2) Based on these params, prepare the environment - create or destroy vm
   instances, create/check disk images, among others
3) Execute the test itself, that will use several of the params defined to
   carry on with its operations, that usually involve:
4) If a test did not raise an exception, it PASSed
5) If a test raised an exception it FAILed
6) Based on what happened during the test, perform cleanup actions, such as
   killing vms, and remove unused disk images.

The list of parameters is obtained by parsing a set of configuration files,
present inside the SourceStructure. The command line options usually modify
even further the parser file, so we can introduce new data in the config
set.

Common Operations -- Listing guests
===================================

If you want to see all guests defined, you can use

::

    ./run -t [test type] --list-guests


This will generate a list of possible guests that can be used for tests,
provided that you have an image with them. The list will show which guests
don't have an image currently available. If you did perform the usual
bootstrap procedure, only JeOS.17.64 will be available.

Now, let's assume you have the image for another guest. Let's say you've
installed Fedora 17, 64 bits, and that --list-guests shows it as downloaded

::

    ./run -t qemu --list-guests
    ... snip...
    16 Fedora.17.32 (missing f17-32.qcow2)
    17 Fedora.17.64
    18 Fedora.8.32 (missing f8-32.qcow2)

You can list all the available tests for Fedora.17.64 (you must use the exact
string printed by the test, minus obviously the index number, that's there
only for informational purposes:

::

    ./run -t qemu -g Fedora.17.64 --list-tests
    ... snip ...
    26 balloon_check.base
    27 balloon_check.balloon-migrate
    28 balloon_check.balloon-shutdown_enlarge
    29 balloon_check.balloon-shutdown_evict
    30 block_mirror
    31 block_stream
    ... snip ...

Then you can execute one in particular. It's the same idea, just copy the
individual test you want and run it:

::

    ./run -t qemu -g Fedora.17.64 --tests balloon_check.balloon-migrate

And it'll run that particular test.

*Tip:* By the rules of the cartesian config files, you can use:

::

    ./run -t qemu -g Fedora.17.64 --tests balloon_check

And it'll run all tests from 26-29. Very useful for large sets, such as
virtio_console and usb - You can just do a:

::

    ./run -t qemu --tests virtio_console
    ... 118 tests ...

::

    ./run -t qemu --tests usb
    ... 64 tests ...

Note that in the examples above, the fact I didn't provide -g means that we're
using the default guest OS, that is, JeOS.
