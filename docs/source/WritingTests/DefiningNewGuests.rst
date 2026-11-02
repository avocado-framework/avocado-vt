=====================
 Defining New Guests
=====================

Let's say you have a guest image that you've carefully prepared, and the JeOS
just doesn't cut it. Here's how you add new guests:

Linux Based Custom Guest
========================

If your guest is Linux based, you can add a config file snippet describing
your test (We have a bunch of pre-set values for linux in the default config).

The drop in directory is

::

    shared/cfg/guest-os/Linux/LinuxCustom

You can add, say, foo.cfg to that dir with the content:

::

    - FooLinux:
        image_name = images/foo-linux

Which would make it possible to specify this custom guest using

::

    $ avocado run migrate..tcp --vt-type qemu --vt-guest-os LinuxCustom.FooLinux
    JOB ID     : 44a399b427c51530ba2fcc37087c100917e1dd8a
    JOB LOG    : /home/lmr/avocado/job-results/job-2015-07-29T03.47-44a399b/job.log
    JOB HTML   : /home/lmr/avocado/job-results/job-2015-07-29T03.47-44a399b/html/results.html
    TESTS      : 3
    (1/3) type_specific.io-github-autotest-qemu.migrate.default.tcp: PASS (31.34 s)
    (2/3) type_specific.io-github-autotest-qemu.migrate.with_set_speed.tcp: PASS (26.99 s)
    (3/3) type_specific.io-github-autotest-qemu.migrate.with_reboot.tcp: PASS (46.40 s)
    RESULTS    : PASS 3 | ERROR 0 | FAIL 0 | SKIP 0 | WARN 0 | INTERRUPT 0
    TIME       : 104.73 s

Provided that you have a file called images/foo-linux.qcow2, if using the
qcow2 format image.

Other useful params to set (not an exhaustive list):

.. code-block:: cfg

    # shell_prompt is a regexp used to match the prompt on aexpect.
    # if your custom os is based of some distro listed in the guest-os
    # dir, you can look on the files and just copy shell_prompt
    shell_prompt = [*]$
    # If you plan to use a raw device, set image_device = yes
    image_raw_device = yes
    # Password of your image
    password = 123456
    # Shell client used (may be telnet or ssh)
    shell_client = ssh
    # Port were the shell client is running
    shell_port = 22
    # File transfer client
    file_transfer_client = scp
    # File transfer port
    file_transfer_port = 22

Ubuntu Autoinstall
==================

Ubuntu live-server installers use Subiquity autoinstall instead of preseed.
Set ``unattended_file`` to a ``.yaml`` or ``.yml`` cloud-config file with a
``#cloud-config`` header and a top-level ``autoinstall:`` mapping. The provided
``unattended/Ubuntu-autoinstall.yaml`` example creates the ``ubuntu`` user with
the test password ``12345678``, enables SSH password login, and powers off when
installation finishes.

The ``Ubuntu.24.04-server.x86_64`` guest supplies an example CD-ROM installation
configuration. Override ``cdrom_cd1`` to use the Ubuntu live-server ISO available
on the host. For another release, use the same installation settings with its
own image and kernel paths:

.. code-block:: cfg

    unattended_install.cdrom:
        cdroms = cd1
        unattended_delivery_method = integrated
        cdrom_unattended = images/ubuntu-server-24-04-64/autoinstall.iso
        cdrom_cd1 = isos/linux/ubuntu-24.04.2-live-server-amd64.iso
        kernel = images/ubuntu-server-24-04-64/vmlinuz
        initrd = images/ubuntu-server-24-04-64/initrd
        boot_path = casper
        unattended_file = unattended/Ubuntu-autoinstall.yaml
        wait_no_ack = yes
        username = ubuntu
        password = 12345678

The installer kernel and initrd are copied from ``casper`` without remastering.
With ``in_cdrom_ks`` (``unattended_delivery_method = integrated``), Avocado VT
uses ``xorriso`` to add ``autoinstall.yaml`` to the root of the installation ISO,
preserving its boot records. The generated ISO replaces ``cdrom_cd1`` for the
installation, and ``autoinstall`` is added to the kernel command line. This
requires Ubuntu 24.04 or newer for the top-level ``autoinstall:`` mapping. It is
the default installation path for the multi-VM suite's Ubuntu 24.04 guest.

With ``extra_cdrom_ks`` (``unattended_delivery_method = cdrom``), Avocado VT
creates a NoCloud seed ISO labelled ``CIDATA`` containing ``user-data`` and
``meta-data``. The seed ISO is attached alongside the Ubuntu installation ISO,
using ``cdroms = cd1 unattended``. Both CD-ROM delivery methods require no
guest-to-host network connection to read the autoinstall configuration.

HTTP delivery remains available through ``http_ks``
(``unattended_delivery_method = url``). Use ``cdroms = cd1`` for this mode.
Avocado VT then adds ``autoinstall ds=nocloud-net;s=http://HOST:PORT/`` to the
kernel command line. The guest must be able to reach that HTTP server; use
``url_auto_ip`` to override the automatically selected host address when needed.
Existing ``.preseed`` and ``.ks`` files retain their previous delivery mechanisms.

See `Providing autoinstall configuration
<https://canonical-subiquity.readthedocs-hosted.com/en/latest/tutorial/providing-autoinstall.html>`_
for the configuration formats and delivery methods.

Windows Based Custom Guest
==========================

If your guest is Linux based, you can add a config file snippet describing
your test (We have a bunch of pre-set values for linux in the default config).

The drop in directory is

::

    shared/cfg/guest-os/Windows/WindowsCustom

You can add, say, foo.cfg to that dir with the content:

::

    - FooWindows:
        image_name = images/foo-windows

Which would make it possible to specify this custom guest using

::

    $ avocado run migrate..tcp --vt-type qemu --vt-guest-os WindowsCustom.FooWindows

Provided that you have a file called images/foo-windows.qcow2.

Other useful params to set (not an exhaustive list):

.. code-block:: cfg

    # If you plan to use a raw device, set image_device = yes
    image_raw_device = yes
    # Attention: Changing the password in this file is not supported,
    # since files in winutils.iso use it.
    username = Administrator
    password = 1q2w3eP
