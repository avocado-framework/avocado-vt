Defining New Guests
===================

Let's say you have a guest image that you've carefully prepared, and the JeOS
just doesn't cut it. Here's how you add new guests:

Linux Based Custom Guest
------------------------

If your guest is Linux based, you can add a config file snippet describing
your test (We have a bunch of pre-set values for linux in the default config).

The drop in directory is

::

    shared/cfg/guest-os/Linux/LinuxCustom

You can add, say, foo.cfg to that dir with the content:

::

    FooLinux:
        image_name = images/foo-linux

Which would make it possible to specify this custom guest using

::

    ./run -t qemu -g LinuxCustom.FooLinux

Provided that you have a file called images/foo-linux.qcow2, if using the
qcow2 format image. If you wish to provide a raw image file, you must use

::

    ./run -t qemu -g LinuxCustom.FooLinux --image-type raw


Other useful params to set (not an exaustive list):

::

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

Windows Based Custom Guest
--------------------------

If your guest is Linux based, you can add a config file snippet describing
your test (We have a bunch of pre-set values for linux in the default config).

The drop in directory is

::

    shared/cfg/guest-os/Windows/WindowsCustom

You can add, say, foo.cfg to that dir with the content:

::

    FooWindows:
        image_name = images/foo-windows

Which would make it possible to specify this custom guest using

::

    ./run -t qemu -g WindowsCustom.FooWindows

Provided that you have a file called images/foo-windows.qcow2, if using the
qcow2 format image. If you wish to provide a raw image file, you must use

::

    ./run -t qemu -g WindowsCustom.FooWindows --image-type raw

Other useful params to set (not an exaustive list):

::

    # If you plan to use a raw device, set image_device = yes
    image_raw_device = yes
    # Attention: Changing the password in this file is not supported,
    # since files in winutils.iso use it.
    username = Administrator
    password = 1q2w3eP

