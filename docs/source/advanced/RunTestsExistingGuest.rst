========================================
Running tests on an existing guest image
========================================

virt-test knows how to install guests, and that's all fine, but most
of the time, users already have a guest image they are working on, and
just want to tell virt-test to use it. Also, virt-test is a large
piece of infrastructure, and it's not really obvious how all the pieces
fit together, so some help is required to dispose the available pieces
conveniently, so users can accomplish their own testing goals. So, let's
get started.

A bit of context on how autotest works
--------------------------------------

The default upstream configuration file instructs autotest to perform
the following tasks:

#. Install a Linux guest, on this case, Fedora 15, due to the fact it is
   publicly available, so *everybody* can try it out. The hardware
   configuration for the VM:

   -  one qcow2 image on an ide bus
   -  one network card, model rtl8139
   -  two cpus
   -  no pci hotplug devices will be attached to this vm
   -  Also, the VM is not going to use hugepage memory explicitly

#. Run a boot test.
#. Run a shutdown test.

::

        # Runs qemu-kvm, f15 64 bit guest OS, install, boot, shutdown
        - @qemu_kvm_f15_quick:
            # We want qemu-kvm for this run
            qemu_binary = /usr/bin/qemu-kvm
            qemu_img_binary = /usr/bin/qemu-img
            only qcow2
            only rtl8139
            only ide
            only smp2
            only no_pci_assignable
            only smallpages
            only Fedora.15.64
            only unattended_install.cdrom, boot, shutdown

This is defined in such a way that the kvm test config system will
generate only 3 tests. Let's see at the tests generated. On the kvm test
dir ``$AUTOTEST_ROOT/client/tests/kvm``, you can call the configuration
parser:

::

    [lmr@freedom kvm]$ ../../common_lib/cartesian_config.py tests.cfg
    dict    1:  smp2.Fedora.15.64.unattended_install.cdrom
    dict    2:  smp2.Fedora.15.64.boot
    dict    3:  smp2.Fedora.15.64.shutdown

You can see on top of the file tests.cfg some *includes* that point us
from where all the test information comes from:

::

    # Copy this file to tests.cfg and edit it.
    #
    # This file contains the test set definitions. Define your test sets here.
    include tests_base.cfg
    include cdkeys.cfg
    include virtio-win.cfg

tests_base.cfg is a pretty large file, that contains a lot of
*variants*, that are blocks defining tests, vm hardware and pre/post
processing directives that control autotest infrastructure behavior. You
can check out the definition of each of the variants restricting the
test sets (qcow2, rtl8139, smp2, no_pci_assignable, smallpages, Fedora
15.64, unattended_install.cdrom, boot, shutdown) on tests_base.cfg.

About guest install
-------------------

It is no mystery that for a good deal of the virtualization tests we are
going to execute, a guest with an *operating system* on its disk image
is needed. To get this OS there, we have some methods defined:

#. Install the VM with the OS CDROM through an engine that interacts
   with the VM using VNC, simulating a human being, called *step
   engine*. This engine works surprisingly well, frequently yielding
   successful installations. However, each *step* is a point of failure
   of the whole process, so we moved towards handing the dirty install
   control to the guest OS itself, as many of them have this capacity.
#. Install the VM using the automated install mechanisms provided by the
   guest OS itself. In windows, we have a mechanism called *answer
   files*, for Fedora and RHEL we have *kickstarts*, and for OpenSUSE we
   have *autoyast*. Of course, other OS, such as debian, also have their
   own mechanism, however they are not currently implemented in autotest
   (hint, hint).

And then an even simpler alternative:

#. Just copy a known good guest OS image, that was already installed,
   and use it. This tends to be faster and less error prone, since the
   install *is already done*, so we don't need to work on failures on
   this step. The inevitable question that arises:

-  *Q. Hey, why don't you just go with that on the first place?*
-  *A. Because installing a guest exercises several aspects of the VM,
   such as disk, network, hardware probing, so on and so forth, so it's
   a good functional test by itself. Also, installing manually a guest
   may work well for a single developer working on his/her patches, but
   certainly does not scale if you need fully automated test done on a
   regular basis, as there is the need of someone going there and making
   the install, which seriously, is a waste of human resources. KVM
   autotest is also a tool for doing such a massively automated test on
   a regular basis.*

Also, this method assumes the least possible for the person running the
tests, as they won't need to have preinstalled guests, and because we
*always get* the same vm, with the same capabilities and same
configuration. Now that we made this point clear, let's explain how to
use your preinstalled guest.

Needed setup for a typical linux guest
--------------------------------------

virt-test relies heavily on *cartesian config files*. Those files use
a flexible file format, defined on :doc:`the file format documentation <../advanced/cartesian/CartesianConfigParametersIntro>`
If you are curious about the
defaults assumed for Linux or Windows guests, you can always check the
file base.cfg.sample, which contains all our guest definitions
(look at the Linux or Windows variant). Without diving too much into it,
it's sufficient to say that you need a guest to have a root password of
123456 and an enabled ssh daemon which will allow you to log in as root.
The password can be also configured through the config files.

Before you start
----------------

#. Make sure you have the appropriate packages installed. You can read
   :doc:`the install prerequesite packages (client section) <../basic/InstallPrerequesitePackages>` for more
   information. For this how to our focus is not to build kvm from git
   repos, so we are assuming you are going to use the default qemu
   installed in the system. However, if you are interested in doing so,
   you might want to recap our docs on :doc:`building qemu-kvm and running unittests <../extra/RunQemuUnittests>`.

Step by step procedure
----------------------

#. Git clone autotest to a convenient location, say $HOME/Code/autotest.
   See :doc:`the download source documentation <../contributing/DownloadSource>`.
   Please do use git and clone the repo to the location mentioned.
#. Execute the ``./run -t qemu --bootstrap`` command (see `the get started documentation <GetStarted>`. Since we are going to
   boot our own guests, you can safely skip each and every iso download
   possible.
#. Edit the file ``tests.cfg``. You can see we have a session overriding
   Custom Guest definitions present on ``tests_base.cfg``. If you want to
   use a raw block device (see
   :doc:`image_raw_device <../advanced/cartesian/CartesianConfigReference-KVM-image_raw_device>`),
   you can uncomment the lines mentioned on the comments. When
   ``image_raw_device = yes``, virt-test will not append a '.qcow2'
   extension to the image name. **Important:** If you opt for a raw
   device, you must comment out the line that appends a base path to
   image names (one that looks like
   ``image_name(_.*)? ?<= /tmp/kvm_autotest_root/images/``)

   ::

       CustomGuestLinux:
           # Here you can override the default login credentials for your custom guest
           username = root
           password = 123456
           image_name = custom_image_linux
           image_size = 10G
           # If you want to use a block device as the vm disk, uncomment the 2 lines
           # below, pointing the image name for the device you want
           #image_name = /dev/mapper/vg_linux_guest
           #image_raw_device = yes

#. Some lines below, you will also find this config snippet. This is for
   the case where you want to specify new base directories for kvm
   autotest to look images, cdroms and floppies.

   ::

       # Modify/comment the following lines if you wish to modify the paths of the
       # image files, ISO files or qemu binaries.
       #
       # As for the defaults:
       # * qemu and qemu-img are expected to be found under /usr/bin/qemu-kvm and
       #   /usr/bin/qemu-img respectively.
       # * All image files are expected under /tmp/kvm_autotest_root/images/
       # * All install iso files are expected under /tmp/kvm_autotest_root/isos/
       # * The parameters cdrom_unattended, floppy, kernel and initrd are generated
       #   by virt-test, so remember to put them under a writable location
       #   (for example, the cdrom share can be read only)
       image_name(_.*)? ?<= /tmp/kvm_autotest_root/images/
       cdrom(_.*)? ?<= /tmp/kvm_autotest_root/
       floppy ?<= /tmp/kvm_autotest_root/

#. Change the fields ``image_name``, ``image_size`` to your liking. Now, the
   **example** test set that uses custom guest configuration can be
   found some lines below:

   ::

           # Runs your own guest image (qcow2, can be adjusted), all migration tests
           # (on a core2 duo laptop with HD and 4GB RAM, F15 host took 3 hours to run)
           # Be warned, disk stress + migration can corrupt your image, so make sure
           # you have proper backups
           - @qemu_kvm_custom_migrate:
               # We want qemu-kvm for this run
               qemu_binary = /usr/bin/qemu-kvm
               qemu_img_binary = /usr/bin/qemu-img
               only qcow2
               only rtl8139
               only ide
               only smp2
               only no_pci_assignable
               only smallpages
               only CustomGuestLinux
               only migrate

#. Since we want to execute this custom migrate test set, we need to
   look at the last couple of lines of the configuration file:

   ::

       # Choose your test list from the testsets defined
       only qemu_kvm_f15_quick

#. This line needs to become

   ::

       # Choose your test list from the testsets defined
       only qemu_kvm_custom_migrate

#. Now, if you haven't changed any of the settings of the previous
   blocks, now our configuration system will run tests with the
   following expectations:

-  qemu-kvm and qemu are under ``/usr/bin/qemu-kvm`` and
   ``/usr/bin/qemu-kvm``, respectively. *Please remember RHEL installs
   qemu-kvm under ``/usr/libexec``*.
-  Our guest image is under
   ``/tmp/kvm_autotest_root/images/custom_image_linux.qcow2``, since the
   test set specifies ``only qcow2``.
-  All current combinations for our migrate tests variant will be
   executed with your custom image. It is never enough to remember that
   some of the tests can corrupt your qcow2 (or raw) image.

#. If you want to verify all tests that the config system will generate,
   you can run the parser to tell you that. This set took 3 hours to run
   on my development laptop setup.

   ::

       [lmr@freedom kvm]$ ../../common_lib/cartesian_config.py tests.cfg
       dict    1:  smp2.CustomGuestLinux.migrate.tcp
       dict    2:  smp2.CustomGuestLinux.migrate.unix
       dict    3:  smp2.CustomGuestLinux.migrate.exec
       dict    4:  smp2.CustomGuestLinux.migrate.mig_cancel
       dict    5:  smp2.CustomGuestLinux.migrate.with_set_speed.tcp
       dict    6:  smp2.CustomGuestLinux.migrate.with_set_speed.unix
       dict    7:  smp2.CustomGuestLinux.migrate.with_set_speed.exec
       dict    8:  smp2.CustomGuestLinux.migrate.with_set_speed.mig_cancel
       dict    9:  smp2.CustomGuestLinux.migrate.with_reboot.tcp
       dict   10:  smp2.CustomGuestLinux.migrate.with_reboot.unix
       dict   11:  smp2.CustomGuestLinux.migrate.with_reboot.exec
       dict   12:  smp2.CustomGuestLinux.migrate.with_reboot.mig_cancel
       dict   13:  smp2.CustomGuestLinux.migrate.with_file_transfer.tcp
       dict   14:  smp2.CustomGuestLinux.migrate.with_file_transfer.unix
       dict   15:  smp2.CustomGuestLinux.migrate.with_file_transfer.exec
       dict   16:  smp2.CustomGuestLinux.migrate.with_file_transfer.mig_cancel
       dict   17:  smp2.CustomGuestLinux.migrate.with_autotest.dbench.tcp
       dict   18:  smp2.CustomGuestLinux.migrate.with_autotest.dbench.unix
       dict   19:  smp2.CustomGuestLinux.migrate.with_autotest.dbench.exec
       dict   20:  smp2.CustomGuestLinux.migrate.with_autotest.dbench.mig_cancel
       dict   21:  smp2.CustomGuestLinux.migrate.with_autotest.stress.tcp
       dict   22:  smp2.CustomGuestLinux.migrate.with_autotest.stress.unix
       dict   23:  smp2.CustomGuestLinux.migrate.with_autotest.stress.exec
       dict   24:  smp2.CustomGuestLinux.migrate.with_autotest.stress.mig_cancel
       dict   25:  smp2.CustomGuestLinux.migrate.with_autotest.monotonic_time.tcp
       dict   26:  smp2.CustomGuestLinux.migrate.with_autotest.monotonic_time.unix
       dict   27:  smp2.CustomGuestLinux.migrate.with_autotest.monotonic_time.exec
       dict   28:  smp2.CustomGuestLinux.migrate.with_autotest.monotonic_time.mig_cancel

#. If you want to make sure virt-test is assigning images to the
   right places, you can tell the config system to print the params
   contents for each test.

   ::

       [lmr@freedom kvm]$ ../../common_lib/cartesian_config.py -c tests.cfg | less
       ... lots of output ...

#. In any of the dicts you should be able to see an ``image_name`` key
   that has something like the below. virt-test will only append
   'image_format' to this path and then use it, so in the case
   mentioned,
   '/tmp/kvm_autotest_root/images/custom_image_linux.qcow2'

   ::

           image_name = /tmp/kvm_autotest_root/images/custom_image_linux

#. After you have verified things, you can run autotest using the
   command line ``get_started.py`` has informed you:

   ::

       $AUTOTEST_ROOT/client/bin/autotest $AUTOTEST_ROOT/client/tests/kvm/control

#. Profit!

Common questions
----------------

-  Q: How do I restrict the test set so it takes less time to run?
-  A: You can look at the output of the cartesian config parser and
   check out the test combinations. If you look at the output above, and
   say you want to run only migration + file transfer tests, your test
   set would look like the below snippet. Make sure you validate your
   changes calling the parser again.

   ::

           # Runs your own guest image (qcow2, can be adjusted), all migration tests
           # (on a core2 duo laptop with HD and 4GB RAM, F15 host took 3 hours to run)
           # Be warned, disk stress + migration can corrupt your image, so make sure
           # you have proper backups
           - @qemu_kvm_custom_migrate:
               # We want qemu-kvm for this run
               qemu_binary = /usr/bin/qemu-kvm
               qemu_img_binary = /usr/bin/qemu-img
               only qcow2
               only rtl8139
               only ide
               only smp2
               only no_pci_assignable
               only smallpages
               only CustomGuestLinux
               only migrate.with_file_transfer

   ::

       [lmr@freedom kvm]$ ../../common_lib/cartesian_config.py tests.cfg
       dict    1:  smp2.CustomGuestLinux.migrate.with_file_transfer.tcp
       dict    2:  smp2.CustomGuestLinux.migrate.with_file_transfer.unix
       dict    3:  smp2.CustomGuestLinux.migrate.with_file_transfer.exec
       dict    4:  smp2.CustomGuestLinux.migrate.with_file_transfer.mig_cancel

