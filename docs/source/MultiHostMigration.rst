==========================
Multi Host Migration Tests
==========================

Running Multi Host Migration Tests
==================================

Avocado-VT is our test suite, but for simplicity purposes it can only run on
a single host. For multi host tests, you'll need the full autotest + Avocado-VT
package, and the procedure is more complex. We'll try to keep this procedure
as objective as possible.

Prerequesites
=============

This guide assumes that:

1) You have at least 2 virt capable machines that have shared storage setup
   in [insert specific path]. Let's call them ``host1.foo.com`` and ``host2.foo.com``.
2) You can ssh into both of those machines without a password (which means
   there is an SSH key setup with the account you're going to use to run
   the tests) as root.
3) The machines should be able to communicate freely, so beware of the potential
   firewall complications. On each of those machines you need a specific NFS mount setup:

* /var/lib/virt_test/isos
* /var/lib/virt_test/steps_data
* /var/lib/virt_test/gpg

They all need to be backed by an NFS share read only. Why read only? Because
it is safer, we exclude the chance to delete this important data by accident.
Besides the data above is only needed in a read only fashion.
fstab example::

    myserver.foo.com:/virt-test/iso /var/lib/virt_test/isos nfs ro,nosuid,nodev,noatime,intr,hard,tcp 0 0
    myserver.foo.com:/virt-test/steps_data  /var/lib/virt_test/steps_data nfs rw,nosuid,nodev,noatime,intr,hard,tcp 0 0
    myserver.foo.com:/virt-test/gpg  /var/lib/virt_test/gpg nfs rw,nosuid,nodev,noatime,intr,hard,tcp 0 0

* /var/lib/virt_test/images
* /var/lib/virt_test/images_archive

Those all need to be backed by an NFS share read write (or any other shared
storage you might have). This is necessary because both hosts need to see
the same coherent storage. fstab example::

    myserver.foo.com:/virt-test/images_archive  /var/lib/virt_test/images_archive nfs rw,nosuid,nodev,noatime,intr,hard,tcp 0 0
    myserver.foo.com:/virt-test/images /var/lib/virt_test/images  nfs rw,nosuid,nodev,noatime,intr,hard,tcp 0 0

The images dir must be populated with the installed guests you want to run
your tests on. They must match the file names used by guest OS in Avocado-VT.
For example, for RHEL 6.4, the image name Avocado-VT uses is::

    rhel64-64.qcow2

double check your files are there::

    $ ls /var/lib/virt_test/images
    $ rhel64-64.qcow2


Setup step by step
==================

First, clone the autotest repo recursively. It's a repo with lots of
submodules, so you'll see a lot of output::

    $ git clone --recursive https://github.com/autotest/autotest.git
    ... lots of output ...

Then, edit the global_config.ini file, and change the key::

    serve_packages_from_autoserv: True

to::

    serve_packages_from_autoserv: False

Then you need to update Avocado-VT's config files and sub tests (that live in
separate repositories that are not git submodules). You don't need to download
the JeOS file in this step, so simply answer 'n' to the quest

Note: The bootstrap procedure described below will be performed automatically
upon running the autoserv command that triggers the test. The problem is that
then you will not be able to see the config files and modify filters prior
to actually running the test. Therefore this documentation will instruct you
to run the steps below manually.

::

    16:11:14 INFO | qemu test config helper
    16:11:14 INFO |
    16:11:14 INFO | 1 - Updating all test providers
    16:11:14 INFO | Fetching git [REP 'git://github.com/autotest/tp-qemu.git' BRANCH 'master'] -> /var/tmp/autotest/client/tests/virt/test-providers.d/downloads/io-github-autotest-qemu
    16:11:17 INFO | git commit ID is 6046958afa1ccab7f22bb1a1a73347d9c6ed3211 (no tag found)
    16:11:17 INFO | Fetching git [REP 'git://github.com/autotest/tp-libvirt.git' BRANCH 'master'] -> /var/tmp/autotest/client/tests/virt/test-providers.d/downloads/io-github-autotest-libvirt
    16:11:19 INFO | git commit ID is edc07c0c4346f9029930b062c573ff6f5433bc53 (no tag found)
    16:11:20 INFO |
    16:11:20 INFO | 2 - Checking the mandatory programs and headers
    16:11:20 INFO | /usr/bin/xz
    16:11:20 INFO | /usr/sbin/tcpdump
    16:11:20 INFO | /usr/bin/nc
    16:11:20 INFO | /sbin/ip
    16:11:20 INFO | /sbin/arping
    16:11:20 INFO | /usr/bin/gcc
    16:11:20 INFO | /usr/include/bits/unistd.h
    16:11:20 INFO | /usr/include/bits/socket.h
    16:11:20 INFO | /usr/include/bits/types.h
    16:11:20 INFO | /usr/include/python2.6/Python.h
    16:11:20 INFO |
    16:11:20 INFO | 3 - Checking the recommended programs
    16:11:20 INFO | Recommended command missing. You may want to install it if not building it from source. Aliases searched: ('qemu-kvm', 'kvm')
    16:11:20 INFO | Recommended command qemu-img missing. You may want to install it if not building from source.
    16:11:20 INFO | Recommended command qemu-io missing. You may want to install it if not building from source.
    16:11:20 INFO |
    16:11:20 INFO | 4 - Verifying directories
    16:11:20 INFO |
    16:11:20 INFO | 5 - Generating config set
    16:11:20 INFO |
    16:11:20 INFO | 6 - Verifying (and possibly downloading) guest image
    16:11:20 INFO | File JeOS 19 x86_64 not present. Do you want to download it? (y/n) n
    16:11:30 INFO |
    16:11:30 INFO | 7 - Checking for modules kvm, kvm-amd
    16:11:30 WARNI| Module kvm is not loaded. You might want to load it
    16:11:30 WARNI| Module kvm-amd is not loaded. You might want to load it
    16:11:30 INFO |
    16:11:30 INFO | 8 - If you wish, take a look at the online docs for more info
    16:11:30 INFO |
    16:11:30 INFO | https://github.com/autotest/virt-test/wiki/GetStarted

Then you need to copy the multihost config file to the appropriate place::

    cp client/tests/virt/test-providers.d/downloads/io-github-autotest-qemu/qemu/cfg/multi-host-tests.cfg client/tests/virt/backends/qemu/cfg/

Now, edit the file::

    server/tests/multihost_migration/control.srv

In there, you have to change the EXTRA_PARAMS to restrict the number of guests
you want to run the tests on. On this example, we're going to restrict our tests
to RHEL 6.4. The particular section of the control file should look like:

.. code-block:: python

    EXTRA_PARAMS = """
    only RHEL.6.4.x86_64
    """

It is important to stress that the guests must be installed for this to work
smoothly. Then the last step would be to run the tests. Using the same convention
for the machine hostnames, here's the command you should use::

    $ server/autotest-remote -m host1.foo.com,host2.foo.com server/tests/multihost_migration/control.srv

Now, you'll see a boatload of output from the autotest remote output. This is
normal, and you should be patient until all the tests are done.


.. _multihost_migration:

Writing Multi Host Migration tests
----------------------------------

Scheme:
~~~~~~~

.. figure:: MultiHostMigration/multihost-migration.png

:download:`Source file for the diagram above (LibreOffice file) <MultiHostMigration/multihost-migration.odg>`


Example:
~~~~~~~~

.. code-block:: python

    class TestMultihostMigration(virt_utils.MultihostMigration):
        def __init__(self, test, params, env):
            super(testMultihostMigration, self).__init__(test, params, env)

        def migration_scenario(self):
            srchost = self.params.get("hosts")[0]
            dsthost = self.params.get("hosts")[1]

            def worker(mig_data):
                vm = env.get_vm("vm1")
                session = vm.wait_for_login(timeout=self.login_timeout)
                session.sendline("nohup dd if=/dev/zero of=/dev/null &")
                session.cmd("killall -0 dd")

            def check_worker(mig_data):
                vm = env.get_vm("vm1")
                session = vm.wait_for_login(timeout=self.login_timeout)
                session.cmd("killall -9 dd")

            # Almost synchronized migration, waiting to end it.
            # Work is started only on first VM.

            self.migrate_wait(["vm1", "vm2"], srchost, dsthost,
                              worker, check_worker)

            # Migration started in different threads.
            # It allows to start multiple migrations simultaneously.

            # Starts one migration without synchronization with work.
            mig1 = self.migrate(["vm1"], srchost, dsthost,
                                worker, check_worker)

            time.sleep(20)

            # Starts another test simultaneously.
            mig2 = self.migrate(["vm2"], srchost, dsthost)
            # Wait for mig2 finish.
            mig2.join()
            mig1.join()

    mig = TestMultihostMigration(test, params, env)
    # Start test.
    mig.run()

When you call:

.. code-block:: python

    mig = TestMultihostMigration(test, params, env)

What happens is

1. VM's disks will be prepared.
2. The synchronization server will be started.
3. All hosts will be synchronized after VM create disks.

When you call the method:

.. code-block:: python

    migrate()

What happens in a diagram is:

+------------------------------------------+-----------------------------------+
|                source                    |             destination           |
+==========================================+===================================+
|                  It prepare VM if machine is not started.                    |
+------------------------------------------+-----------------------------------+
|            Start work on VM.             |                                   |
+------------------------------------------+-----------------------------------+
|          ``mig.migrate_vms_src()``       |   ``mig.migrate_vms_dest()``      |
+------------------------------------------+-----------------------------------+
|                                          | Check work on VM after migration. |
+------------------------------------------+-----------------------------------+
|                       Wait for finish migration on all hosts.                |
+------------------------------------------+-----------------------------------+

It's important to note that the migrations are made using the ``tcp`` protocol,
since the others don't support multi host migration.

.. code-block:: python

    def migrate_vms_src(self, mig_data):
        vm = mig_data.vms[0]
        logging.info("Start migrating now...")
        vm.migrate(mig_data.dst, mig_data.vm_ports)


This example migrates only the first machine defined in migration. Better example
is in ``virt_utils.MultihostMigration.migrate_vms_src``. This function migrates
all machines defined for migration.
