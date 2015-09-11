===============================
Getting started with avocado-vt
===============================

Here's a reference guide on how to get the plugin setup and running.
We'll assume that you will use avocado and avocado-vt through RPMS,
and will also provide pointers on how to get the latest released RPMS.
If you are working on plugin development and want to perform the same
procedure, but using git repos instead of RPMS, the
`README.rst file <https://github.com/avocado-framework/avocado-vt/blob/master/README.rst>`__
at the top level of the avocado-vt repository has the detailed procedure.

1. Please add the avocado RPM repository, following instructions from
   `this link <http://avocado-framework.readthedocs.org/en/latest/GetStartedGuide.html#installing-avocado>`__.

2. Assuming you have followed the instructions above, the yum/dnf package
   manager already has the information necessary to find the package
   `avocado-plugins-vt`. Install it::

    $ yum install avocado-plugins-vt

4. Run avocado-vt's bootstrap procedure for the test backend (qemu, libvirt,
   v2v, openvswitch, among others) of your interest. We'll use qemu as an example::

    $ avocado vt-bootstrap --vt-type qemu

6. Let's test if things went well by listing the avocado plugins. In the avocado source dir, do::

    $ avocado plugins

   That command should show the loaded plugins, and hopefully no errors. The relevant lines will be::

    virt_test_compat_bootstrap  Implements the avocado 'vt-bootstrap' subcommand
    virt_test_compat_runner  Implements the avocado virt test options
    virt_test_compat_lister  Implements the avocado virt test options

7. The next test is to see if virt-tests are also listed in the output of the
   command `avocado list` (you might leave out the --vt-type if you use default)::

    $ avocado list --vt-type qemu --verbose

   This should list a large amount of tests (over 1900 virt related tests)::

    ACCESS_DENIED: 0
    BROKEN_SYMLINK: 0
    BUGGY: 0
    INSTRUMENTED: 49
    MISSING: 0
    NOT_A_TEST: 27
    SIMPLE: 3
    VT: 1906

8. Assuming all is well, you can try running one virt-test::

    $ avocado run type_specific.io-github-autotest-qemu.migrate.default.tcp
    JOB ID     : <id>
    JOB LOG    : /home/<user>/avocado/job-results/job-2015-06-15T19.46-1c3da89/job.log
    JOB HTML   : /home/<user>/avocado/job-results/job-2015-06-15T19.46-1c3da89/html/results.html
    TESTS      : 1
    (1/1) type_specific.io-github-autotest-qemu.migrate.default.tcp: PASS (95.76 s)
    PASS       : 1
    ERROR      : 0
    FAIL       : 0
    SKIP       : 0
    WARN       : 0
    INTERRUPT  : 0
    TIME       : 95.76 s

If you have trouble executing the steps provided in this guide, you have a few
options:

* Send an e-mail to `the avocado mailing list <https://www.redhat.com/mailman/listinfo/avocado-devel>`__.
* Open an issue on `the avocado-vt github area <https://github.com/avocado-framework/avocado-vt/issues/new>`__.
* We also hang out on `IRC (irc.oftc.net, #avocado) <irc://irc.oftc.net/#avocado>`__.
