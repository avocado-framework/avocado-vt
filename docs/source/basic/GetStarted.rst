===============
Getting Started
===============

Pre-requisites
--------------

#. A supported host platforms: Red Hat Enterprise Linux (RHEL) or Fedora.
   OpenSUSE should also work, but currently autotest is still
   not packaged for it, which means you have to clone autotest and put its path
   in an env variable so virt tests can find the autotest libs.
   Debian/Ubuntu now have a new experimental package that allows one to run
   the virt tests in a failry straight forward way.

#. :doc:`Install software packages (RHEL/Fedora) <../basic/InstallPrerequesitePackages>`
#. :doc:`Install software packages (Debian/Ubuntu) <../basic/InstallPrerequesitePackagesDebian>`
#. A copy of the :doc:`virt test source <../contributing/DownloadSource>`

For the impatient
-----------------

1) Clone the virt test repo

::

    git clone git://github.com/autotest/virt-test.git


2) Get into the base dir

::

    cd virt-test

3) Run the bootstrap procedure. For example, if you want to run
   the qemu subtest, you will run:

::

    ./run -t qemu --bootstrap

This script will check if you have the minimum requirements for the test
(required commands and includes), and download the JeOS image. You can omit
running this script, since the code of this script also gets to run when you
call the test runner, but it is discouraged. Explicitly running get_started.py
first is iteractive, and gives you a better idea of what is going on.


4) For qemu and libvirt subtests, the default test set does not require
   root. However, other tests might fail due to lack of privileges.

::

    $ ./run -t qemu

or

::

    # ./run -t libvirt


If you ran get_started.py, the test runner should just run the test. If you
didn't, the runner will trigger the environment setup procedure:

1) Create the /var/tmp/libvirt_test dir to hold images and isos
2) Download the JeOS image (180 MB, takes about 3 minutes on a fast connection)
   and uncompress it (takes about a minute on an HDD laptop). p7ip has to
   be present.
3) Run a predefined set of tests.


Running different tests
-----------------------

You can list the available tests to run by using the flag --list-tests

::

    $ ./run -t qemu --list-tests
    (will print a numbered list of tests, with a paginator)

Then you can pass tests that interest you with --tests "list of tests", for
example:

1) qemu

::

    $ ./run -t qemu --tests "migrate timedrift file_transfer"

2) Libvirt requires first importing the JeOS image. However, this cannot be done
   if the guest already exists.  Therefore, it's wise to also conclude a set with the
   remove_guest.without_disk test.

::

    # ./run -t libvirt --tests "unattended_install.import.import boot reboot remove_guest.without_disk"


Checking the results
--------------------

The test runner will produce a debug log, that will be useful to debug
problems:

::

    $ ./run -t qemu --tests usb
    Running setup. Please wait...
    SETUP: PASS (13.52 s)
    DATA DIR: /home/lmr/virt_test
    DEBUG LOG: /home/lmr/Code/virt-test.git/logs/run-2014-01-27-14.25.31/debug.log
    TESTS: 203
    (1/203) type_specific.io-github-autotest-qemu.usb.usb_boot.usb_kbd.without_usb_hub.uhci: PASS (25.47 s)
    (2/203) type_specific.io-github-autotest-qemu.usb.usb_boot.usb_kbd.without_usb_hub.ehci: PASS (23.53 s)
    (3/203) type_specific.io-github-autotest-qemu.usb.usb_boot.usb_kbd.without_usb_hub.xhci: PASS (24.34 s)
    ...

Here you can see that the debug log is in `/home/lmr/Code/virt-test.git/logs/run-2014-01-27-14.25.31/debug.log`.
For convenience, the most recent log is pointed to by the `logs/latest` symlink.
