===============
Getting Started
===============

Pre-requisites
--------------

#. A supported host platforms: Red Hat Enterprise Linux (RHEL) or Fedora.

#. :doc:`Install software packages (RHEL/Fedora) <../basic/InstallPrerequesitePackages>`

For the impatient
-----------------

3) Run the bootstrap procedure. For example, if you want to run
   the qemu tests, you will run:

::

    avocado vt-bootstrap --vt-type qemu

This script will check if you have the minimum requirements for the test
(required commands and includes), and download the JeOS image.

4) For qemu and libvirt subtests, the default test set does not require
   root. However, other tests might fail due to lack of privileges.

::

    $ avocado run migrate..tcp --vt-type qemu

Running different tests
-----------------------

You can list the available tests to run by using the flag --list-tests

::

    $ avocado list --vt-type qemu
    (will print a numbered list of tests, with a paginator)

Then you can pass tests that interest you with --tests "list of tests", for
example:

1) qemu

::

    $ avocado run migrate..tcp --vt-type qemu

Checking the results
--------------------

The test runner will produce a debug log, that will be useful to debug
problems, as well as an HTML report:

::

    avocado run migrate..tcp --vt-type qemu --open-browser
    JOB ID     : 44a399b427c51530ba2fcc37087c100917e1dd8a
    JOB LOG    : /home/user/avocado/job-results/job-2015-07-29T03.47-44a399b/job.log
    JOB HTML   : /home/user/avocado/job-results/job-2015-07-29T03.47-44a399b/html/results.html
    TESTS      : 3
    (1/3) type_specific.io-github-autotest-qemu.migrate.default.tcp: PASS (31.34 s)
    (2/3) type_specific.io-github-autotest-qemu.migrate.with_set_speed.tcp: PASS (26.99 s)
    (3/3) type_specific.io-github-autotest-qemu.migrate.with_reboot.tcp: PASS (46.40 s)
    RESULTS    : PASS 3 | ERROR 0 | FAIL 0 | SKIP 0 | WARN 0 | INTERRUPT 0
    TIME       : 104.73 s

For convenience, the most recent log is pointed to by the `~/avocado/job-results/latest/debug.log` symlink.
