=============================================
Links with downloadable images for virt tests
=============================================

This is a central location that we aim to keep
up to date with locations of iso files that
might be needed for testing.

Update: Now we have a central location to define
such downloads. In the source tree:

::

    shared/downloads/

Contains a bunch of .ini files, each one with
download definitions. It is expected that this
will be more up to date than this page. You can
see the available downloads and download the files
using:


::

    scripts/download_manager.py


Winutils ISO
============

The windows utils file can be currently found at:

https://avocado-project.org/data/assets/winutils.iso

How to update `winutils.iso`
----------------------------

That's basically a collection of files useful for windows testing. If you want
to update that file, you'll have to pick that iso file, extract it to a directory,
make changes, remaster the iso and upload back to the main location.


Windows virtio drivers ISO
==========================

In Avocado we mainly use fedora/RHEL based windows virtio drivers ISO that
can be obtained from:

https://docs.fedoraproject.org/en-US/quick-docs/creating-windows-virtual-machines-using-virtio-drivers/index.html

JeOS image
==========

You can find the JeOS images currently available here:

https://avocado-project.org/data/assets/jeos-23-64.qcow2.xz

https://avocado-project.org/data/assets/SHA1SUM_JEOS23_XZ

You can browse through https://avocado-project.org/data/assets/jeos/ and find
other JeOS versions available.

How to update JeOS
------------------

The JeOS can be updated by installing it, just like a normal OS. You can do
that for example with ``avocado-vt``, selecting an unattended install test. In
this example, we're going to use the unattended install using https kickstart
and network install::

    $ avocado run io-github-autotest-qemu.unattended_install.url.http_ks.default_install.aio_native

The JeOS kickstart has a trick to fill the qcow2 image with zeros, so that we
can squeeze these zeros later with qemu img. Once the image is installed, you
can use our helper script, located at ``scripts/package_jeos.py`` in the
avocado-vt source tree. That script uses qemu-img to trim the zeros of the
image, ensuring that the resulting qcow2 image is the smallest possible. The
command is similar to::

    $ qemu-img convert -f qcow2 -O qcow2 jeos-file-backup.qcow2 jeos-file.qcow2

Then it'll compress it using xz, to save space and speed up downloads for
``avocado-vt`` users. The command is similar to::

    $ xz jeos-file.qcow2.xz jeos-file.qcow2

As mentioned, the script is supposed to help you with the process.
