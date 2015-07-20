Install prerequesite packages
===================================================

We need git and autotest, not available on RHEL repos. So, on RHEL hosts run first:

::

     rpm -ivh http://download.fedora.redhat.com/pub/epel/5/i386/epel-release-5-4.noarch.rpm

To install `EPEL <http://fedoraproject.org/wiki/EPEL/FAQ>`_ repos. It is
important to note that EPEL is needed with the sole purpose of providing
a git RHEL package. If you can manage to install git from somewhere
else, then this is not necessary. Check
`here <http://fedoraproject.org/wiki/EPEL/FAQ#How_can_I_install_the_packages_from_the_EPEL_software_repository.3F>`_
for up to date EPEL RPM repo location.

Install the following packages:

#. Install a toolchain in your host, which you can do with Fedora and RHEL with:

::

   yum groupinstall "Development Tools"

#. Install tcpdump, necessary to determine guest IPs automatically

::

   yum install tcpdump

#. Install nc, necessary to get output from the serial device and other
   qemu devices

::

   yum install nmap-ncat


#. Install the p7zip file archiver so you can uncompress the JeOS [2] image.

::

   yum install p7zip

#. Install the autotest-framework package, to provide the needed autotest libs.

::

   yum install --enablerepo=updates-testing autotest-framework

#. Install the fakeroot package, if you want to install from the CD Ubuntu and
Debian servers without requiring root:

::

   yum install fakeroot


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

     yum install git

So you can checkout the source code. If you want to test the distro provided
qemu-kvm binary, you can install:

::

     yum install qemu-kvm qemu-kvm-tools


To run libvirt tests, it's required to install the virt-install utility, for the basic purpose of building and cloning virtual machines.

::

     yum install virt-install

To run all tests that involve filedescriptor passing, you need python-devel.
The reason is, this test suite is compatible with python 2.4, whereas a
std lib to pass filedescriptors was only introduced in python 3.2. Therefore,
we had to introduce a C python extension that is compiled on demand.

::

    yum install python-devel.


It's useful to also install:

::

     yum install python-imaging

Not vital, but very handy to do imaging conversion from ppm to jpeg and
png (allows for smaller images).



Tests that are not part of the default JeOS set
-----------------------------------------------

If you want to run guest install tests, you need to be able to
create floppies and isos to hold kickstart files:

::

     yum install mkisofs

For newer distros, such as Fedora, you'll need:

::

     yum install genisoimage

Both packages provide the same functionality, needed to create iso
images that will be used during the guest installation process. You can
also execute


Network tests
-------------

Last bug not least, now we depend on libvirt to provide us a stable, working bridge.
* By default, the kvm test uses user networking, so this is not entirely
necessary. However, non root and user space networking make a good deal
of the hardcode networking tests to not work. If you might want to use
bridges eventually:

::

    yum install libvirt bridge-utils

Make sure libvirtd is started:

::

    [lmr@freedom autotest.lmr]$ service libvirtd start

Make sure the libvirt bridge shows up on the output of brctl show:

::

    [lmr@freedom autotest.lmr]$ brctl show
    bridge name bridge id       STP enabled interfaces
    virbr0      8000.525400678eec   yes     virbr0-nic
