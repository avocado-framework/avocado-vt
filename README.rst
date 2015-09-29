Avocado VT Plugin
=================

Avocado Virt Test Compatibility is a plugin that lets you
execute virtualization related tests, with all conveniences
provided by avocado.

Getting started with avocado-vt
===============================

Here's a reference guide on how to get the plugin setup and running,
assuming you are using git repos for avocado and avocado-vt. Please keep in
mind that the recommended way of using avocado is through RPM packages, that
you can see how to install in our online documentation:

http://avocado-vt.readthedocs.org/en/latest/GetStartedGuide.html

If you want to go ahead and use the git repos (you're hacking on avocado and
avocado-vt), then follow the instructions below:

1. Make sure you have avocado and avocado-vt repositories cloned in the same dir.
   then you can execute our `make link` target::

    $ make link

2. Avocado-VT has a number of dependencies on other software packages. You can
   install those dependencies via pip, or some other method of your preference
   (install distro packages, for example). As an example, on a recent Fedora
   install (> 22), the dependencies can be installed with::

    $ yum install autotest-framework p7zip tcpdump iproute iputils gcc glibc-headers python-devel nc aexpect

   This assumes you are using our software repositories to install packages
   such as `aexpect` (see the GetStartedGuide.html link above). If you use other
   distros, we trust you'll take the above as a reference and will find the
   correspondent software packages to install. For example, you can install
   autotest-framework and `aexpect` using pip::

    $ pip install autotest aexpect

   Keep in mind that this text file might be outdated, and that usually our spec file
   (avocado-plugins-vt.spec) tends to be a good reference as well.

3. Run the bootstrap procedure for the test backend (qemu, libvirt, v2v,
   openvswitch, among others) of your interest. We'll use qemu as an example::

    $ scripts/avocado vt-bootstrap --vt-type qemu

   That command will generate the following symlinks in your avocado source code
   dir (assuming you have only avocado-vt, and not avocado-virt)::

    avocado/core/plugins/virt_test.py
    avocado/core/plugins/virt_test_list.py
    etc/avocado/conf.d/virt-test.conf
    virttest

   Also, it's important to note that this process will create a new directory
   in your home dir, by default, ~/avocado. This directory will be populated
   with a number of config files (and other data files) necessary to run the
   avocado-vt tests.

4. Let's test if things went well by listing the avocado plugins. In the avocado source dir, do::

    $ scripts/avocado plugins

   That command should show the loaded plugins, and hopefully no errors. The relevant lines will be::

    virt_test_compat_bootstrap  Implements the avocado 'vt-bootstrap' subcommand
    virt_test_compat_runner  Implements the avocado virt test options
    virt_test_compat_lister  Implements the avocado virt test options

5. The next test is to see if virt-tests are also listed in the output of the
   command `avocado list`::

    $ scripts/avocado list --verbose

   This should list a large amount of tests (over 1900 virt related tests)::

    ACCESS_DENIED: 0
    BROKEN_SYMLINK: 0
    BUGGY: 0
    INSTRUMENTED: 52
    MISSING: 0
    NOT_A_TEST: 27
    SIMPLE: 3
    VT: 1923

6. Assuming all is well, you can try running one virt-test::

    $ scripts/avocado run type_specific.io-github-autotest-qemu.migrate.default.tcp
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
