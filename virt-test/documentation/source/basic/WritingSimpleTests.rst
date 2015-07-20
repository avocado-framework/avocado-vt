
Writing your own virt test
==================================

In this article, we'll talk about:

#. Where the test files are located
#. Write a simple test file
#. Try out your new test, send it to the mailing list


Where the virt test files are located ?
---------------------------------------

The subtests can be located in 2 subdirs:

-  tests - These tests are written in a fairly virt
   technology agnostic way, so they can be used by other virt
   technologies testing. More specifically, they do not use the vm
   monitor.

   ::

    $ ls
    autotest_control.py  fail.py              iofuzz.py          module_probe.py          ping.py             shutdown.py                 vlan.py
    boot.py              file_transfer.py     ioquit.py          multicast.py             pxe.py              skip.py                     warning.py
    boot_savevm.py       fillup_disk.py       iozone_windows.py  netperf.py               rv_connect.py       softlockup.py               watchdog.py
    build.py             fullscreen_setup.py  jumbo.py           netstress_kill_guest.py  rv_copyandpaste.py  stress_boot.py              whql_client_install.py
    cfg                  guest_s4.py          kdump.py           nfs_corrupt.py           rv_disconnect.py    trans_hugepage_defrag.py    whql_submission.py
    clock_getres.py      guest_test.py        linux_s3.py        nicdriver_unload.py      rv_fullscreen.py    trans_hugepage.py           yum_update.py
    dd_test.py           image_copy.py        lvm.py             nic_promisc.py           rv_input.py         trans_hugepage_swapping.py
    ethtool.py           __init__.py          mac_change.py      ntttcp.py                save_restore.py     unattended_install.py

-  qemu/tests - These are tests that do use
   specific qemu infrastructure, specifically the qemu monitor. other
   virt technologies can't use it so they go here.

   ::

    $ ls
    9p.py             __init__.py                                     multi_disk.py                 qemu_io_blkdebug.py       timedrift.py
    balloon_check.py  kernel_install.py                               negative_create.py            qemu_iotests.py           timedrift_with_migration.py
    block_mirror.py   ksm_overcommit.py                               nic_bonding.py                qmp_basic.py              timedrift_with_reboot.py
    block_stream.py   migration_multi_host_cancel.py                  nic_hotplug.py                qmp_basic_rhel6.py        timedrift_with_stop.py
    cdrom.py          migration_multi_host_downtime_and_speed.py      nmi_bsod_catch.py             seabios.py                time_manage.py
    cfg               migration_multi_host_ping_pong.py               nmi_watchdog.py               set_link.py               unittest_qemuctl.py
    cgroup.py         migration_multi_host.py                         pci_hotplug.py                smbios_table.py           unittest.py
    cpuflags.py       migration_multi_host_with_file_transfer.py      perf_qemu.py                   sr_iov_hotplug.py         usb.py
    cpu_hotplug.py    migration_multi_host_with_speed_measurement.py  performance.py                sr_iov_hotunplug.py       virtio_console.py
    enospc.py         migration.py                                    physical_resources_check.py   stepmaker.py              vmstop.py
    floppy.py         migration_with_file_transfer.py                 qemu_guest_agent.py           steps.py
    getfd.py          migration_with_reboot.py                        qemu_guest_agent_snapshot.py  stop_continue.py
    hdparm.py         migration_with_speed_measurement.py             qemu_img.py                   system_reset_bootable.py

So the thumb rule is, if it uses the qemu monitor, you stick it into qemu/tests,
if it doesn't, you can stick it into the tests/ dir.

Write our own, drop-in 'uptime' test - Step by Step procedure
-------------------------------------------------------------

Now, let's go and write our uptime test, which only purpose in life is
to pick up a living guest, connect to it via ssh, and return its uptime.

#. Git clone virt_test.git to a convenient location, say $HOME/Code/virt-test.
   See `the download source documentation <../contributing/DownloadSource>`.
   Please do use git and clone the repo to the location mentioned.

#. Our uptime test won't need any qemu specific feature. Thinking about
   it, we only need a vm object and stablish an ssh session to it, so we
   can run the command. So we can store our brand new test under
   ``tests``. At the autotest root location:

   ::

    [lmr@freedom virt-test.git]$ touch tests/uptime.py
    [lmr@freedom virt-test.git]$ git add tests/uptime.py

#. Ok, so that's a start. So, we have *at least* to implement a
   function ``run_uptime``. Let's start with it and just put the keyword
   pass, which is a no op. Our test will be like:

   ::

       def run_uptime(test, params, env):
           """
           Docstring describing uptime.
           """
           pass

#. Now, what is the API we need to grab a VM from our test environment?
   Our env object has a method, ``get_vm``, that will pick up a given vm
   name stored in our environment. Some of them have aliases. ``main_vm``
   contains the name of the main vm present in the environment, which
   is, most of the time, ``vm1``. ``env.get_vm`` returns a vm object, which
   we'll store on the variable vm. It'll be like this:

   ::

       def run_uptime(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])

#. A vm object has lots of interesting methods, which we plan on documenting
   them more thoroughly, but for
   now, we want to ensure that this VM is alive and functional, at least
   from a qemu process standpoint. So, we'll call the method
   ``verify_alive()``, which will verify whether the qemu process is
   functional and if the monitors, if any exist, are functional. If any
   of these conditions are not satisfied due to any problem, an
   exception will be thrown and the test will fail. This requirement is
   because sometimes due to a bug the vm process might be dead on the
   water, or the monitors are not responding.

   ::

       def run_uptime(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()

#. Next step, we want to log into the vm. the vm method that does return
   a remote session object is called ``wait_for_login()``, and as one of
   the parameters, it allows you to adjust the timeout, that is, the
   time we want to wait to see if we can grab an ssh prompt. We have top
   level variable ``login_timeout``, and it is a good practice to
   retrieve it and pass its value to ``wait_for_login()``, so if for
   some reason we're running on a slower host, the increase in one
   variable will affect all tests. Note that it is completely OK to just
   override this value, or pass nothing to ``wait_for_login()``, since
   this method does have a default timeout value. Back to business,
   picking up login timeout from our dict of parameters:

   ::

       def run_uptime(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))


#. Now we'll call ``wait_for_login()`` and pass the timeout to it,
   storing the resulting session object on a variable named session.

   ::

       def run_uptime(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))
           session = vm.wait_for_login(timeout=timeout)


#. The qemu test will do its best to grab this session, if it can't due
   to a timeout or other reason it'll throw a failure, failing the test.
   Assuming that things went well, now you have a session object, that
   allows you to type in commands on your guest and retrieve the
   outputs. So most of the time, we can get the output of these commands
   throught the method ``cmd()``. It will type in the command, grab the
   stdin and stdout, return them so you can store it in a variable, and
   if the exit code of the command is != 0, it'll throw a
   aexpect.ShellError?. So getting the output of the unix command uptime
   is as simple as calling ``cmd()`` with 'uptime' as a parameter and
   storing the result in a variable called uptime:

   ::

       def run_uptime(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))
           session = vm.wait_for_login(timeout=timeout)
           uptime = session.cmd('uptime')

#. If you want to just print this value so it can be seen on the test
   logs, just log the value of uptime using the logging library. Since
   that is all we want to do, we may close the remote connection, to
   avoid ssh/rss sessions lying around your test machine, with the
   method ``close()``. Now, note that all failures that might happen
   here are implicitly handled by the methods called. If a test
   went from its beginning to its end without unhandled exceptions,
   autotest assumes the test automatically as PASSed, *no need to mark a
   test as explicitly passed*. If you have explicit points of failure,
   for more complex tests, you might want to add some exception raising.

   ::

       def run_uptime(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))
           session = vm.wait_for_login(timeout=timeout)
           uptime = session.cmd("uptime")
           logging.info("Guest uptime result is: %s", uptime)
           session.close()

#. Now, I deliberately introduced a bug on this code just to show you
   guys how to use some tools to find and remove trivial bugs on your
   code. I strongly encourage you guys to check your code with the
   script called run_pylint.py, located at the utils directory at the
   top of your $AUTOTEST_ROOT. This tool calls internally the other
   python tool called pylint to catch bugs on autotest code. I use it so
   much the utils dir of my devel autotest tree is on my $PATH. So, to
   check our new uptime code, we can call (important, if you don't have
   pylint install it with ``yum install pylint`` or equivalent for your
   distro):

   ::

        [lmr@freedom virt-test.git]$ tools/run_pylint.py tests/uptime.py -q
        ************* Module virt-test.git.tests.uptime
        E0602: 10,4:run_uptime: Undefined variable 'logging'


#. Ouch. So there's this undefined variable called logging on line 10 of
   the code. It's because I forgot to import the logging library, which
   is a python library to handle info, debug, warning messages. Let's Fix it
   and the code becomes:

   ::

       import logging

       def run_uptime(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))
           session = vm.wait_for_login(timeout=timeout)
           uptime = session.cmd("uptime")
           logging.info("Guest uptime result is: %s", uptime)
           session.close()

#. Let's re-run ``run_pylint.py`` to see if it's happy with the code
   generated:

   ::

        [lmr@freedom virt-test.git]$ tools/run_pylint.py tests/uptime.py -q
        [lmr@freedom virt-test.git]$

#. So we're good. Nice! Now, as good indentation does matter to python,
   we have another small utility called reindent.py, that will fix
   indentation problems, and cut trailing whitespaces on your code. Very
   nice for tidying up your test before submission.

   ::

        [lmr@freedom virt-test.git]$ tools/reindent.py tests/uptime.py

#. I also use run_pylint with no -q catch small things such as wrong spacing
   around operators and other subtle issues that go against PEP 8 and
   the `coding style
   document <https://github.com/autotest/autotest/blob/master/CODING_STYLE>`_.
   Please take pylint's output with a *handful* of salt, you don't need
   to work each and every issue that pylint finds, I use it to find
   unused imports and other minor things.

   ::

        [lmr@freedom virt-test.git]$ tools/run_pylint.py tests/uptime.py
        ************* Module virt-test.git.tests.uptime
        C0111:  1,0: Missing docstring
        C0103:  7,4:run_uptime: Invalid name "vm" (should match [a-z_][a-z0-9_]{2,30}$)
        W0613:  3,15:run_uptime: Unused argument 'test'

#. These other complaints you don't really need to fix. Due to the tests
   design, they all use 3 arguments, 'vm' is a shorthand that we have been
   using for a long time as a variable name to hold a VM object, and the only
   docstring we'd like you to fill is the one in the run_uptime function.

#. Now, you can test your code. When listing the qemu tests your new test should
   appear in the list:


   ::

   ./run -t qemu --list-tests


#. Now, you can run your test to see if everything went good.

   ::

        [lmr@freedom virt-test.git]$ ./run -t qemu --tests uptime
        SETUP: PASS (1.10 s)
        DATA DIR: /home/lmr/virt_test
        DEBUG LOG: /home/lmr/Code/virt-test.git/logs/run-2012-11-28-13.13.29/debug.log
        TESTS: 1
        (1/1) uptime: PASS (23.30 s)

#. Ok, so now, we have something that can be git commited and sent to
   the mailing list

   ::

        diff --git a/tests/uptime.py b/tests/uptime.py
        index e69de29..65d46fa 100644
        --- a/tests/uptime.py
        +++ b/tests/uptime.py
        @@ -0,0 +1,13 @@
        +import logging
        +
        +def run_uptime(test, params, env):
        +    """
        +    Docstring describing uptime.
        +    """
        +    vm = env.get_vm(params["main_vm"])
        +    vm.verify_alive()
        +    timeout = float(params.get("login_timeout", 240))
        +    session = vm.wait_for_login(timeout=timeout)
        +    uptime = session.cmd("uptime")
        +    logging.info("Guest uptime result is: %s", uptime)
        +    session.close()

#. Oh, we forgot to add a decent docstring description. So doing it:

   ::

       import logging

       def run_uptime(test, params, env):

           """
           Uptime test for virt guests:

           1) Boot up a VM.
           2) Stablish a remote connection to it.
           3) Run the 'uptime' command and log its results.

           :param test: QEMU test object.
           :param params: Dictionary with the test parameters.
           :param env: Dictionary with test environment.
           """

           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))
           session = vm.wait_for_login(timeout=timeout)
           uptime = session.cmd("uptime")
           logging.info("Guest uptime result is: %s", uptime)
           session.close()

#. git commit signing it, put a proper description, then send it with
   git send-email. Profit!
