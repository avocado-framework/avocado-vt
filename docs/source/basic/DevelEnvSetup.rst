Development workflow after the Repository Split
===============================================

1) Clone virt-test
2) `Fork the test provider you want to contribute to in github <https://help.github.com/articles/fork-a-repo>`
3) Clone the forked repository. In this example, we'll assume you cloned the forked repo to

::

    /home/user/code/tp-libvirt

4) Add a file in virt-test/test-providers.d, with a name you like. We'll assume you chose

::

    user-libvirt.ini

5) Contents of user-libvirt.ini:

::

    [provider]
    uri: file:///home/user/code/tp-qemu
    [libvirt]
    subdir: libvirt/
    [libguestfs]
    subdir: libguestfs/
    [lvsb]
    subdir: lvsb/
    [v2v]
    subdir: v2v/

6) This should be enough. Now, when you use --list-tests, you'll be able to see entries like:

::

    ...
    1 user-libvirt.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_native
    2 user-libvirt.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads
    3 user-libvirt.unattended_install.cdrom.extra_cdrom_ks.perf.aio_native
    ...

7) Modify tests, or add new ones to your heart's content. When you're happy with your changes, you may create branches and `send us pull requests <https://help.github.com/articles/using-pull-requests>`__.

That should be it. Let us know if you have any doubts about the process through
:doc:`the mailing list <../contributing/ContactInfo>` or
`opening an issue <https://github.com/autotest/virt-test/issues/new>`__.
