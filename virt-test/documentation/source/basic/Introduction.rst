=========================
Introduction to Virt Test
=========================

Virt-test's main purpose is to serve as an automated regression testing tool
for virt developers, and for doing regular automated testing of virt technologies
(provided you use it with the server testing infrastructure).

Autotest is a project that aims to provide tools and libraries to
perform automated testing on the linux platform. `virt-test` is a
subproject under the autotest umbrella. For more information on
autotest, see `the autotest home page <http://autotest.github.com/>`_.

`virt-test` aims to be a centralizing project for most of the virt
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

For an overview about virt-test, how this project was created, its
goals, structure, and how to develop simple tests, you can refer to the
`KVM forum 2010 slides <Introduction/2010-forum-Kvm-autotest.pdf>`_.
