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

Other useful params to set (not an exaustive list):

.. code-block:: cfg

    # If you plan to use a raw device, set image_device = yes
    image_raw_device = yes
    # Attention: Changing the password in this file is not supported,
    # since files in winutils.iso use it.
    username = Administrator
    password = 1q2w3eP
