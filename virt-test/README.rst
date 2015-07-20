======================================
Linux Virtualization Tests (virt-test)
======================================

Really quick start guide
------------------------

The most convenient distro to run virt-test on is Fedora,
since we have autotest libs officially packaged on this distro [1].

It is similarly easy to set things up on a RHEL box, but then
you need to enable the EPEL repos [2] to install the needed packages.

The most recent addition to this list is Ubuntu/Debian. New repos were
set with a new autotest package. Learn how to add the proper repos and
install your packages on [3].


Install dependencies
--------------------

Install the p7zip file archiver so you can uncompress the JeOS [4] image.

Red Hat based::

# yum install p7zip

Debian based::

# apt-get install p7zip-full

Install the autotest-framework package, to provide the needed autotest libs.

Red Hat based::

# yum install autotest-framework

Debian based (needs to enable repo, see [3])::

# apt-get install autotest

Some tests might need some other dependencies, such as the migrate
using file descriptors, that requires a working toolchain and python-devel,
and generating VM videos, that requires python-gstreamer.

For such cases, it is best that you refer to the more complete documentation:

http://virt-test.readthedocs.org/en/latest/basic/InstallPrerequesitePackages.html

http://virt-test.readthedocs.org/en/latest/basic/InstallPrerequesitePackagesDebian.html


Execute the bootstrap script
------------------------

Let's say you're interested in the qemu tests::

./run -t qemu --bootstrap

The script can help you to setup a data dir, copy the sample config files
to actual config files, and download the JeOS image.

Execute the runner script
-------------------------

You can execute the main runner script, called run. The script offers you
some options, all explained in the script help. A really really simple execution
of the script for qemu tests is::

./run -t qemu

This will execute a subset of the tests available.

Note: If you execute the runner before the bootstrap, things will work,
but then you won't get prompted and the runner will download the JeOS
automatically.

Writing your first test
-----------------------

http://virt-test.readthedocs.org/en/latest/basic/WritingSimpleTests.html

Is your tutorial to write your first test. Alternatively, you
can copy the simple template test we have under the samples
directory to the appropriate test directory, and start hacking
from there. Example: You want to create a qemu specific test
for the jelly functionality. You have to do::

$ cp samples/template.py qemu/tests/jelly.py

And then edit the template file accordingly.

[1] If you want to use it without the packaged rpm, you need to have a clone
of the autotest code (git://github.com/autotest/autotest.git) and set the
env variable AUTOTEST_PATH pointing to the path of the clone. We do have
plans to package the libs to more distributions.

[2] http://fedoraproject.org/wiki/EPEL/FAQ#How_can_I_install_the_packages_from_the_EPEL_software_repository.3F

[3] https://github.com/autotest/virt-test/wiki/InstallPrerequesitePackagesDebian

[4] JeOS: Minimal guest OS image (x86_64)


Description
-----------

virt-test is a Linux virtualization test suite, intended to be used in
conjunction with the autotest framework [1], although it can be also used
separately, on a virt developer's machine, to run tests quicker and smaller
in scope, as an auxiliary tool of the development process.

This test suite aims to have test tools for a wide range of testing scenarios:

-  Guest OS install, for both Windows (WinXP - Win7) and Linux (RHEL,
   Fedora, OpenSUSE) and any generic one, through a 'step engine' mechanism.
-  Serial output for Linux guests
-  Migration, networking, timedrift and other types of tests
-  Monitor control for both human and QMP protocols
-  Build and use qemu using various methods (source tarball, git repo,
   rpm)
-  Performance testing
-  Call other kvm test projects, such as kvm-unit-tests

We support x86\_64 hosts with hardware virtualization support (AMD and
Intel), and Intel 32 and 64 bit guest operating systems, and work is underway
to support PPC hosts.

[1] http://autotest.github.com/ - Autotest is a project that aims to
provide tools and libraries to perform automated testing on the linux
platform. Autotest is a modular framework, and this suite can be used as
a submodule of the client module. If you do not want to use or know about
autotest, this is fine too, and we'll provide documentation and tools to
perform development style testing with it.


Basic Troubleshooting
---------------------

If you have problems with the basic usage described here, it's possible
that there's some local change in your working copy of virt-test. These
changes can come in (at least) two different categories:

- Code changes, which you can check with the git tools (try "git diff"
  and "git branch" first)
- Configuration changes that can you reset with "update_config.py"

If you find that you have local changes in the code, please try to reset
your checked out copy to upstream's master by running::

$ git checkout master
$ git pull

You can also update your tests (both qemu, libvirt and others) by doing::

$ ./run -t qemu --bootstrap --update-providers

And then, reset you configuration. If you're going to run qemu tests, run::

$ ./run -t qemu --update-config

If you're still having problems after these basic troubleshoot steps,
please contact us!


Documentation
-------------

Virt Test comes with in tree documentation, that can be built with ``sphinx``.
A publicly available build of the latest master branch documentation and
releases can be seen on `read the docs <https://readthedocs.org/>`__:

http://virt-test.readthedocs.org/en/latest/index.html

If you want to build the documentation, here are the instructions:

1) Make sure you have the package ``python-sphinx`` installed. For Fedora::

    $ sudo yum install python-sphinx

2) For Ubuntu/Debian::

    $ sudo apt-get install python-sphinx

3) Optionally, you can install the read the docs theme, that will make your
   in-tree documentation to look just like in the online version::

    $ sudo pip install sphinx_rtd_theme

4) Build the docs::

    $ make -C documentation html

5) Once done, point your browser to::

    $ [your-browser] docs/build/html/index.html
