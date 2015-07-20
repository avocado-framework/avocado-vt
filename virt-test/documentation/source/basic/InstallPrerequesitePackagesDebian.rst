Install prerequesite packages - Debian
===================================================

Keep in mind that the current autotest package is a work in progress. For the
purposes of running virt-tests it is fine, but it needs a lot of improvements
until it can become a more 'official' package.

The autotest debian package repo can be found at https://launchpad.net/~lmr/+archive/autotest,
and you can add the repos on your system putting the following on /etc/apt/sources.list:

::

   deb http://ppa.launchpad.net/lmr/autotest/ubuntu raring main
   deb-src http://ppa.launchpad.net/lmr/autotest/ubuntu raring main

Then update your software list:

::

   apt-get update

This has been tested with Ubuntu 12.04, 12.10 and 13.04.

Install the following packages:


#. Install the autotest-framework package, to provide the needed autotest libs.

::

   apt-get install autotest


#. Install the p7zip file archiver so you can uncompress the JeOS [2] image.

::

   apt-get install p7zip-full


#. Install tcpdump, necessary to determine guest IPs automatically

::

   apt-get install tcpdump

#. Install nc, necessary to get output from the serial device and other
   qemu devices

::

   apt-get install netcat-openbsd


#. Install a toolchain in your host, which you can do on Debian and Ubuntu with:

::

   apt-get install build-essential

#. Install fakeroot if you want to install from CD debian and ubuntu, not
requiring root:

::

   apt-get install fakeroot

So you install the core autotest libraries to run the tests.

*If* you don't install the autotest-framework package (say, your distro still
doesn't have autotest packages, or you don't want to install the rpm),
you'll have to clone an autotest tree and export this path as the
AUTOTEST_PATH variable, both as root and as your regular user. One could put the
following on their ~/.bashrc file:

::

    export AUTOTEST_PATH="/path/to/autotest"

where this AUTOTEST_PATH will guide the run script to set up the needed
libraries for all tests to work.


For other packages:

::

     apt-get install git

So you can checkout the source code. If you want to test the distro provided
qemu-kvm binary, you can install:

::

     apt-get install qemu-kvm qemu-utils

To run libvirt tests, it's required to install the virt-install utility, for the basic purpose of building and cloning virtual machines.

::

     apt-get install virtinst

To run all tests that involve filedescriptor passing, you need python-all-dev.
The reason is, this test suite is compatible with python 2.4, whereas a
std lib to pass filedescriptors was only introduced in python 3.2. Therefore,
we had to introduce a C python extension that is compiled on demand.

::

    apt-get install python-all-dev.


It's useful to also install:

::

     apt-get install python-imaging

Not vital, but very handy to do imaging conversion from ppm to jpeg and
png (allows for smaller images).



Tests that are not part of the default JeOS set
-----------------------------------------------

If you want to run guest install tests, you need to be able to
create floppies and isos to hold kickstart files:

::

     apt-get install genisoimage


Network tests
-------------

Last bug not least, now we depend on libvirt to provide us a stable, working bridge.
* By default, the kvm test uses user networking, so this is not entirely
necessary. However, non root and user space networking make a good deal
of the hardcode networking tests to not work. If you might want to use
bridges eventually:

::

    apt-get install libvirt-bin python-libvirt bridge-utils

Make sure libvirtd is started:

::

    [lmr@freedom autotest.lmr]$ service libvirtd start

Make sure the libvirt bridge shows up on the output of brctl show:

::

    [lmr@freedom autotest.lmr]$ brctl show
    bridge name bridge id       STP enabled interfaces
    virbr0      8000.525400678eec   yes     virbr0-nic
