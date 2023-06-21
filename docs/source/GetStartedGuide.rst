.. _get-started:

===============
Getting Started
===============

The first step towards using Avocado-VT is, quite obviously, installing it.

Installing Avocado-VT
=====================

Avocado-VT is an Avocado plugin, therefore you are going to need both in
order to be able to execute the tests.

Both are primarily written in Python, so a standard Python installation is
possible and often preferable.

If you just want to use the plugin to run tests you might prefer to use
packages from your system's package manager if available; this way non-python
dependencies, esp. Avocado, are also taken care of automatically.

You can find more details about the Avocado installation
`here <https://avocado-framework.readthedocs.io/en/latest/guides/user/chapters/installing.html>`__.


Installing via PIP
------------------

Pip is useful when it comes to python dependencies, but it fails
in non-python ones. List of non-python requirements based on Fedora
package names is::

    $ dnf install xz tcpdump iproute iputils gcc glibc-headers nc git

Then you can get Avocado-VT via pip::

    $ pip install git+https://github.com/avocado-framework/avocado-vt

Or by manually cloning it from github::

    $ git clone https://github.com/avocado-framework/avocado-vt
    $ cd avocado-vt
    $ pip install .

It's recommended to use ``pip`` even for local install as it treats
requirements differently and the use of ``python setup.py install``
might fail.

Installing via system package manager
-------------------------------------

Installing Avocado-VT on Fedora or Enterprise Linux is a matter of
installing the `avocado-plugins-vt` package. Install it with::

    $ yum install avocado-plugins-vt

Which takes care of all the dependencies (python and non-python ones).

Setup Avocado-VT with sources
-----------------------------

If you intend use avocado from sources, clone it into the same parent directory
as Avocado sources and use ``make link`` from the Avocado sources directory.
Details about this can be found `here <https://avocado-framework.readthedocs.io/en/latest/guides/contributor/chapters/environment.html#installing-in-develop-mode>`__.

.. _run_bootstrap:

Bootstrapping Avocado-VT
========================

After the package, a bootstrap process must be run. Choose your test backend
(qemu, libvirt, v2v, openvswitch, etc) and run the `vt-bootstrap` command. Example::

    $ avocado vt-bootstrap --vt-type qemu

.. note:: If you don't intend to use ``JeOS`` and don't want to install the
   ``xz`` you can use ``avocado vt-bootstrap --vt-type qemu --vt-guest-os
   $OS_OF_YOUR_CHOICE`` which bypasses the ``xz`` check.

The output should be similar to::

    12:02:10 INFO | qemu test config helper
    12:02:10 INFO |
    12:02:10 INFO | 1 - Updating all test providers
    12:02:10 INFO |
    12:02:10 INFO | 2 - Checking the mandatory programs and headers
    12:02:10 INFO | /bin/xz OK
    12:02:10 INFO | /sbin/tcpdump OK
    ...
    12:02:11 INFO | /usr/include/asm/unistd.h OK
    12:02:11 INFO |
    12:02:11 INFO | 3 - Checking the recommended programs
    12:02:11 INFO | /bin/qemu-kvm OK
    12:02:11 INFO | /bin/qemu-img OK
    12:02:11 INFO | /bin/qemu-io OK
    ...
    12:02:33 INFO | 7 - Checking for modules kvm, kvm-intel
    12:02:33 DEBUG| Module kvm loaded
    12:02:33 DEBUG| Module kvm-intel loaded
    12:02:33 INFO |
    12:02:33 INFO | 8 - If you wish, you may take a look at the online docs for more info
    12:02:33 INFO |
    12:02:33 INFO | http://avocado-vt.readthedocs.org/

If there are missing requirements, please install them and re-run `vt-bootstrap`.

.. note:: Recommended programs might be needed for Avocado to correctly
          recognize test cases for your test backend or for test cases
          to run correctly.

.. warning:: When you bootstrap avocado-vt the parallel run of avocado nrunner
             will be disabled by default, because the avocado-vt doesn't support
             parallel tests. If you run test suite without vt tests,  you can
             enable parallel run by `run.max_parallel_tasks` config variable.

First steps with Avocado-VT
===========================

Let's check if things went well by listing the Avocado plugins::

    $ avocado plugins

That command should show the loaded plugins, and hopefully no errors. The relevant lines will be::

    Plugins that add new commands (avocado.plugins.cli.cmd):
    vt-bootstrap Avocado VT - implements the 'vt-bootstrap' subcommand
    ...
    Plugins that add new options to commands (avocado.plugins.cli):
    vt      Avocado VT/virt-test support to 'run' command
    vt-list Avocado-VT/virt-test support for 'list' command

Then let's list the tests available with::

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

.. note:: If no test cases are listed make sure you installed recommended
          programs on your system, s. "Bootstrapping Avocado-VT".

Now let's run a virt test::

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
