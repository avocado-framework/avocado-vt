.. _about-avocado-vt:

About Avocado-VT
================

Avocado-VT is a compatibility plugin that lets you execute virtualization
related tests (then known as virt-test), with all conveniences provided by
Avocado.

Its main purpose is to serve as an automated regression testing tool
for virt developers, and for doing regular automated testing of virt technologies
(provided you use it with the server testing infrastructure).

Avocado-VT aims to be a centralizing project for most of the virt
functional and performance testing needs. We cover:

-  Guest OS install, for both Windows (WinXP - Win7) and Linux (RHEL,
   Fedora, OpenSUSE and others through step engine mechanism)
-  Serial output for Linux guests
-  Migration, networking, timedrift and other types of tests

For the qemu subtests, we can do things like:

-  Monitor control for both human and QMP protocols
-  Build and use qemu using various methods (source tarball, git repo,
   rpm)
-  Some level of performance testing can be made.
-  The KVM unit tests can be run comfortably from inside virt-test,
   we do have full integration with the unittest execution

We support x86\_64 hosts with hardware virtualization support (AMD and
Intel), and Intel 32 and 64 bit guest operating systems.

.. _about-virt-test:

About virt-test
---------------

Virt-test is the project that became Avocado-VT. It used to live under
the Autotest umbrella, under:

http://github.com/autotest/virt-test

That repository is now frozen and only available at that location for
historical purposes.
