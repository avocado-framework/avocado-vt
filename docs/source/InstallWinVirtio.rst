=================================================
Installing Windows virtio drivers with Avocado-VT
=================================================

So, you want to use Avocado-VT to install windows guests. You also
want them to be installed with the paravirtualized drivers developed for
windows. You have come to the right place.

A bit of context on windows virtio drivers install
--------------------------------------------------

This method of install so far covers the storage (viostor) and network
(NetKVM) drivers. Avocado-VT uses a boot floppy with a Windows answer
file in order to perform unattended install of windows guests. For winXP
and win2003, the unattended files are simple .ini files, while for
win2008 and later, the unattended files are XML files.

In order to install the virtio drivers during guest install, KVM
autotest has to inform the windows install programs \*where\* to find
the drivers. So, we work from the following assumptions:

#. You already have an iso file that contains windows virtio drivers
   (inf files) for both netkvm and viostor. If you are unsure how to
   generate that iso, there's an example script under contrib, inside
   the kvm test directory. Here is an example of how the files inside
   this cd would be organized, assuming the iso image is mounted under
   ``/tmp/virtio-win`` (the actual cd has more files, but we took only
   the parts that concern to the example, win7 64 bits).

::

    /tmp/virtio-win/
    /tmp/virtio-win/vista
    /tmp/virtio-win/vista/amd64
    /tmp/virtio-win/vista/amd64/netkvm.cat
    /tmp/virtio-win/vista/amd64/netkvm.inf
    /tmp/virtio-win/vista/amd64/netkvm.pdb
    /tmp/virtio-win/vista/amd64/netkvm.sys
    /tmp/virtio-win/vista/amd64/netkvmco.dll
    /tmp/virtio-win/vista/amd64/readme.doc
    /tmp/virtio-win/win7
    /tmp/virtio-win/win7/amd64
    /tmp/virtio-win/win7/amd64/balloon.cat
    /tmp/virtio-win/win7/amd64/balloon.inf
    /tmp/virtio-win/win7/amd64/balloon.pdb
    /tmp/virtio-win/win7/amd64/balloon.sys
    /tmp/virtio-win/win7/amd64/blnsvr.exe
    /tmp/virtio-win/win7/amd64/blnsvr.pdb
    /tmp/virtio-win/win7/amd64/vioser.cat
    /tmp/virtio-win/win7/amd64/vioser.inf
    /tmp/virtio-win/win7/amd64/vioser.pdb
    /tmp/virtio-win/win7/amd64/vioser.sys
    /tmp/virtio-win/win7/amd64/vioser-test.exe
    /tmp/virtio-win/win7/amd64/vioser-test.pdb
    /tmp/virtio-win/win7/amd64/viostor.cat
    /tmp/virtio-win/win7/amd64/viostor.inf
    /tmp/virtio-win/win7/amd64/viostor.pdb
    /tmp/virtio-win/win7/amd64/viostor.sys
    /tmp/virtio-win/win7/amd64/wdfcoinstaller01009.dll
    ...

If you are planning on installing WinXP or Win2003, you should also have
a pre-made floppy disk image with the virtio drivers \*and\* a
configuration file that the installer program will read to fetch the
right drivers from it. Unfortunately, I don't have much info on how to
build that file, you probably would have the image already assembled if
you are willing to test those guest OS.

So you have to map the paths of your cd containing the drivers on the
config variables. We hope to improve this in cooperation with the virtio
drivers team.

Step by step procedure
----------------------

We are assuming you already have the virtio cd properly assembled with
you, as well as windows iso files that \*do match the ones provided in
our test\_base.cfg.sample\*. Don't worry though, we try as much as
possible to use files from MSDN, to standardize.

We will use win7 64 bits (non sp1) as the example, so the CD you'd need
is:

::

        cdrom_cd1 = isos/windows/en_windows_7_ultimate_x86_dvd_x15-65921.iso
        sha1sum_cd1 = 5395dc4b38f7bdb1e005ff414deedfdb16dbf610

This file can be downloaded from the MSDN site, so you can verify the
SHA1 sum of it matches.

#. Git clone autotest to a convenient location, say $HOME/Code/autotest.
   See :doc:`the download source documentation <../contributing/DownloadSource>`
   Please do use git and clone the repo to the location mentioned.
#. Execute the ``get_started.py`` script (see the `get started documentation <../GetStartedGuide>`.
   It will create the directories where we expect the cd files to be
   available. You don't need to download the Fedora 14 DVD, but you do
   need to download the winutils.iso. Our configuration is based on
   RHEL/Fedora based version that can be obtained from `here <https://docs.fedoraproject.org/en-US/quick-docs/creating-windows-virtual-machines-using-virtio-drivers/index.html>` and
   need to be placed in ``/tmp/kvm_autotest_root/isos/windows``).
   Please, do read the
   documentation mentioned on the script to avoid missing packages
   installed and other misconfiguration.
#. Create a windows dir under ``/tmp/kvm_autotest_root/isos``
#. Copy your windows 7 iso to ``/tmp/kvm_autotest_root/isos/windows``
#. Edit the file cdkeys.cfg and put the windows 7 64 bit key on that
   file
#. Edit the file win-virtio.cfg and verify if the paths are correct. You
   can see that by looking this session:

   ::

               64:
                   unattended_install.cdrom, whql.support_vm_install:
                       # Look at your cd structure and see where the drivers are
                       # actually located (viostor and netkvm)
                       virtio_storage_path = 'F:\win7\amd64'
                       virtio_network_path = 'F:\vista\amd64'

                       # Uncomment if you have a nw driver installer on the iso
                       #virtio_network_installer_path = 'F:\RHEV-Network64.msi'

#. If you are using the cd with the layout mentioned on the beginning of
   this article, the paths are already correct. However, if they're
   different (more likely), you have to adjust paths. Don't forget to
   read and do all the config on win-virtio.cfg file as instructed by
   the comments.
#. On tests.cfg, you have to enable virtio install of windows 7. On the
   block below, you have to change ``only rtl8139`` to
   ``only virtio_net`` and ``only ide`` to ``only virtio-blk``. You are
   informing autotest that you only want a vm with virtio hard disk and
   network device installed.

   ::

           # Runs qemu-kvm, Windows Vista 64 bit guest OS, install, boot, shutdown
           - @qemu_kvm_windows_quick:
               # We want qemu-kvm for this run
               qemu_binary = /usr/bin/qemu-kvm
               qemu_img_binary = /usr/bin/qemu-img
               # Only qcow2 file format
               only qcow2
               # Only rtl8139 for nw card (default on qemu-kvm)
               only rtl8139
               # Only ide hard drives
               only ide
               # qemu-kvm will start only with -smp 2 (2 processors)
               only smp2
               # No PCI assignable devices
               only no_pci_assignable
               # No large memory pages
               only smallpages
               # Operating system choice
               only Win7.64
               # Subtest choice. You can modify that line to add more subtests
               only unattended_install.cdrom, boot, shutdown

#. You have to change the bottom of tests.cfg to look like the below,
   Which means you are informing autotest to only run the test set
   mentioned above, rather than the default, that installs Fedora 15.

   ::

       only qemu_kvm_windows_quick

#. As informed on the output of ``get_started.py``, the command you can
   execute to run autotest is (please run this AS ROOT or sudo)

   ::

       $ $HOME/Code/autotest/client/bin/autotest $HOME/Code/autotest/client/tests/kvm/control

#. Profit! You automated install of Windows 7 with the virtio drivers
   will be carried out.

If you want to install other guests, as you might imagine, you can
change ``only Win7.64`` with other guests, say ``only Win2008.64.sp2``.
Now, during the first time you perform your installs, it's good to watch
the installation to see if there aren't problems such as a **wrong cd
key** preventing your install from happening. Avocado-VT prints the
qemu command line used, so you can see which vnc display you can connect
to to watch your vm being installed.

