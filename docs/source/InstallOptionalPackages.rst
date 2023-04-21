===========================
 Install Optional Packages
===========================

Some packages are not set in the Avocado-VT as hard dependencies,
because they may only be required depending on specific use cases.

If you run into problems while running specific tests, please verify
if installing the mentioned packages fixes your problem.

Fedora and EL
=============

Install the following packages:

#. Install a toolchain in your host, which you can do with Fedora and RHEL with:

::

    $ yum groupinstall "Development Tools"

#. Install tcpdump, necessary to determine guest IPs automatically

::

    $ yum install tcpdump

#. Install nc, necessary to get output from the serial device and other
   qemu devices

::

    $ yum install nmap-ncat


#. Install the xz file archiver so you can uncompress the JeOS [2] image.

::

    $ yum install xz

#. Install the autotest-framework package, to provide the needed autotest libs.

::

    $ yum install --enablerepo=updates-testing autotest-framework

#. Install the fakeroot package, if you want to install from the CD Ubuntu and
Debian servers without requiring root:

::

    $ yum install fakeroot


*If* you don't install the autotest-framework package (say, your distro still
doesn't have autotest packages, or you don't want to install the rpm),
you'll have to clone an autotest tree and export this path as the
AUTOTEST_PATH variable, both as root and as your regular user. One could put the
following on their ~/.bashrc file:

::

    $ export AUTOTEST_PATH="/path/to/autotest"

where this AUTOTEST_PATH will guide the run script to set up the needed
libraries for all tests to work.


For other packages:

::

    $ yum install git

So you can checkout the source code. If you want to test the distro provided
qemu-kvm binary, you can install:

::

    $ yum install qemu-kvm qemu-kvm-tools


To run libvirt tests, it's required to install the virt-install utility, for
the basic purpose of building and cloning virtual machines.

::

    $ yum install virt-install


It's useful to also install:

::

    $ yum install python-imaging

Not vital, but very handy to do imaging conversion from ppm to jpeg and
png (allows for smaller images).



Tests that are not part of the default JeOS set
-----------------------------------------------

If you want to run guest install tests, you need to be able to
create floppies and isos to hold kickstart files:

::

    $ yum install mkisofs

For newer distros, such as Fedora, you'll need:

::

    $ yum install genisoimage

Both packages provide the same functionality, needed to create iso
images that will be used during the guest installation process. You can
also execute


Network tests
-------------

Last but not least, now we depend on libvirt to provide us a stable, working bridge.
* By default, the kvm test uses user networking, so this is not entirely
necessary. However, non root and user space networking make a good deal
of the hardcode networking tests to not work. If you might want to use
bridges eventually:

::

    $ yum install libvirt bridge-utils

Make sure libvirtd is started:

::

    $ service libvirtd start

Make sure the libvirt bridge shows up on the output of brctl show:

::

    $ brctl show
    bridge name bridge id       STP enabled interfaces
    virbr0      8000.525400678eec   yes     virbr0-nic

Debian
======

Keep in mind that the current autotest package is a work in progress. For the
purposes of running virt-tests it is fine, but it needs a lot of improvements
until it can become a more 'official' package.

The autotest debian package repo can be found at https://launchpad.net/~lmr/+archive/autotest,
and you can add the repos on your system putting the following on /etc/apt/sources.list:

::

    $ deb http://ppa.launchpad.net/lmr/autotest/ubuntu raring main
    $ deb-src http://ppa.launchpad.net/lmr/autotest/ubuntu raring main

Then update your software list:

::

    $ apt-get update

This has been tested with Ubuntu 12.04, 12.10 and 13.04.

Install the following packages:


#. Install the autotest-framework package, to provide the needed autotest libs.

::

    $ apt-get install autotest


#. Install the xz-utils file archiver so you can uncompress the JeOS [2] image.

::

    $ apt-get install xz-utils


#. Install tcpdump, necessary to determine guest IPs automatically

::

    $ apt-get install tcpdump

#. Install nc, necessary to get output from the serial device and other
   qemu devices

::

    $ apt-get install netcat-openbsd


#. Install a toolchain in your host, which you can do on Debian and Ubuntu with:

::

    $ apt-get install build-essential

#. Install fakeroot if you want to install from CD debian and ubuntu, not
requiring root:

::

    $ apt-get install fakeroot

So you install the core autotest libraries to run the tests.

*If* you don't install the autotest-framework package (say, your distro still
doesn't have autotest packages, or you don't want to install the rpm),
you'll have to clone an autotest tree and export this path as the
AUTOTEST_PATH variable, both as root and as your regular user. One could put the
following on their ~/.bashrc file:

::

    $ export AUTOTEST_PATH="/path/to/autotest"

where this AUTOTEST_PATH will guide the run script to set up the needed
libraries for all tests to work.


For other packages:

::

    $ apt-get install git

So you can checkout the source code. If you want to test the distro provided
qemu-kvm binary, you can install:

::

    $ apt-get install qemu-kvm qemu-utils

To run libvirt tests, it's required to install the virt-install utility, for the basic purpose of building and cloning virtual machines.

::

    $ apt-get install virtinst

To run all tests that involve filedescriptor passing, you need python-all-dev.
The reason is, this test suite is compatible with python 2.4, whereas a
std lib to pass filedescriptors was only introduced in python 3.2. Therefore,
we had to introduce a C python extension that is compiled on demand.

::

    $ apt-get install python-all-dev.


It's useful to also install:

::

    $ apt-get install python-imaging

Not vital, but very handy to do imaging conversion from ppm to jpeg and
png (allows for smaller images).



Tests that are not part of the default JeOS set
-----------------------------------------------

If you want to run guest install tests, you need to be able to
create floppies and isos to hold kickstart files:

::

    $ apt-get install genisoimage


Network tests
-------------

Last but not least, now we depend on libvirt to provide us a stable, working bridge.
* By default, the kvm test uses user networking, so this is not entirely
necessary. However, non root and user space networking make a good deal
of the hardcode networking tests to not work. If you might want to use
bridges eventually:

::

    $ apt-get install libvirt-bin python-libvirt bridge-utils

Make sure libvirtd is started:

::

    $ service libvirtd start

Make sure the libvirt bridge shows up on the output of brctl show:

::

    $ brctl show
    bridge name bridge id       STP enabled interfaces
    virbr0      8000.525400678eec   yes     virbr0-nic
