===============================================
Development workflow after the Repository Split
===============================================

1. Fork the test provider you want to contribute to in github

https://help.github.com/articles/fork-a-repo

2. Clone the forked repository. In this example, we'll assume you cloned the forked repo to

::

    /home/user/code/tp-libvirt

3. Add a file in ``~/avocado/data/avocado-vt/test-providers.d``, with a name you like. We'll assume you chose

::

    user-libvirt.ini

4. Contents of user-libvirt.ini:

::

    [provider]
    uri: file:///home/user/code/tp-libvirt
    [libvirt]
    subdir: libvirt/
    [libguestfs]
    subdir: libguestfs/
    [lvsb]
    subdir: lvsb/
    [v2v]
    subdir: v2v/

5. This should be enough. Now, when you use ``--list-tests``, you'll be able to see entries like:

::

    ...
    1 user-libvirt.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_native
    2 user-libvirt.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads
    3 user-libvirt.unattended_install.cdrom.extra_cdrom_ks.perf.aio_native
    ...

6. Modify tests, or add new ones to your heart's content. When you're happy with your changes, you may create branches and `send us pull requests <https://help.github.com/articles/using-pull-requests>`__.
