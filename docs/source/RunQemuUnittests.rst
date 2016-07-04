===========================
Running QEMU kvm-unit-tests
===========================

Currently there are two ways to run kvm-unit-tests. Newer one with per test
results method is `Run kvm-unit-tests in avocado`_ and the older one
`Run kvm-unit-tests in avocado-vt`_ which requires manual modifications and
only reports overall results.


Run kvm-unit-tests in avocado
=============================

There is a contrib script to run kvm-unit-test using `external-runner`
Avocado feature. It optionally downloads the latest kvm-unit-test from
Git, compiles it and runs the tests inside avocado.

The contrib script is located in ``$AVOCADO/contrib/testsuites/run-kvm-unit-test.sh``
or can be downloaded from:
https://raw.githubusercontent.com/avocado-framework/avocado/master/contrib/testsuites/run-kvm-unit-test.sh

Then you simply run it and wait for results::

    $ ./contrib/testsuites/run-kvm-unit-test.sh
    JOB ID     : ca00d570f03b4942368ec9c407d69a881d98eb9d
    JOB LOG    : /home/medic/avocado/job-results/job-2016-07-04T09.38-ca00d57/job.log
    TESTS      : 38
     (01/38) access: PASS (4.77 s)
     (02/38) apic: PASS (5.10 s)
     (03/38) debug: PASS (1.82 s)
     (04/38) emulator:  ^C
    Interrupt requested. Waiting 2 seconds for test to finish (ignoring new Ctrl+C until then)

    INTERRUPTED (0.84 s)
    RESULTS    : PASS 3 | ERROR 0 | FAIL 0 | SKIP 34 | WARN 0 | INTERRUPT 1
    JOB HTML   : /home/medic/avocado/job-results/job-2016-07-04T09.38-ca00d57/html/results.html
    TESTS TIME : 12.54 s

.. note:: You can specify various options including the avocado arguments.
          Use the `-h` to see them all (eg. wildcard to specify tests pattern
          or path to avoid (re)downloading of the kvm-unit-test)


Run kvm-unit-tests in avocado-vt
================================

For a while now, qemu-kvm does contain a unittest suite that can be used
to assess the behavior of some KVM subsystems. Ideally, they are
supposed to PASS, provided you are running both the latest qemu and
the latest linux KVM tree. Avocado-VT for quite a long time has
support for running them in an automated way. It's a good opportunity to
put your git branch to unittest, starting from a clean state (KVM
autotest will fetch from your git tree, leaving your actual development
tree intact and doing things from scratch, and that is less likely to
mask problems).

A bit of context on Avocado-VT build tests
------------------------------------------

People usually don't know that Avocado-VT has support to build and
install QEMU/KVM for testing purposes, from many different software sources.
You can:

#. Build qemu-kvm from a git repo (most common choice for developers
   hacking on code)
#. Install qemu-kvm from an rpm file (people testing a newly built rpm
   package)
#. Install qemu-kvm straight from the Red Hat build systems (Koji is the
   instance of the build system for Fedora, Brew is the same, but for
   RHEL. With this we can perform quality control on both Fedora and
   RHEL packages, trying to anticipate breakages before the packages hit
   users)

For this article, we are going to focus on git based builds. Also, we
are focusing on Fedora and RHEL. We'll try to write the article in a
pretty generic fashion, you are welcome to improve this with details on
how to do the same on your favorite linux distribution.

Before you start
----------------

You need to verify that you can actually build qemu-kvm from source, as
well as the unittest suite.

#. Make sure you have the appropriate packages installed. You can read
   :doc:`the install prerequesite packages (client) section <InstallOptionalPackages>` for more
   information.

Step by step procedure
----------------------

#. Git clone autotest to a convenient location, say ``$HOME/Code/autotest``.
   See :doc:`the download source documentation <../contributing/DownloadSource>`
   Please do use git and clone the repo to the location mentioned.
#. Execute the ``get_started.py`` script (see
   :doc:`the get started documentation <GetStartedGuide>`. If you just want
   to run
   unittests, you can safely skip each and every iso download possible,
   as *qemu-kvm will straight boot small kernel images (the unittests)*
   rather than full blown OS installs.
#. As running unittests is something that's fairly independent of other
   Avocado-VT testing you can do, and it's something people are
   interested in, we prepared a *special control file* and a *special
   configuration file* for it. On the kvm directory, you can see the
   files ``unittests.cfg`` ``control.unittests``. You only need to edit
   ``unittests.cfg``.
#. The file ``unittests.cfg`` is a stand alone configuration for running
   unittests. It is comprised by a build variant and a unittests
   variant. Edit the file, it'll look like:

   ::

       ... bunch of params needed for the Avocado-VT preprocessor
       # Tests
       variants:
           - build:
               type = build
               vms = ''
               start_vm = no
               # Load modules built/installed by the build test?
               load_modules = no
               # Save the results of this build on test.resultsdir?
               save_results = no
               variants:
                   - git:
                       mode = git
                       user_git_repo = git://git.kernel.org/pub/scm/virt/kvm/qemu-kvm.git
                       user_branch = next
                       user_lbranch = next
                       test_git_repo = git://git.kernel.org/pub/scm/virt/kvm/kvm-unit-tests.git

           - unittest:
               type = unittest
               vms = ''
               start_vm = no
               unittest_timeout = 600
               testdev = yes
               extra_params += " -S"
               # In case you want to execute only a subset of the tests defined on the
               # unittests.cfg file on qemu-kvm, uncomment and edit test_list
               #test_list = idt_test hypercall vmexit realmode

       only build.git unittest

#. As you can see above, you have places to specify both the userspace
   git repo and the unittest git repo. You are then free to replace
   ``user_git_repo`` with your own git repo. It can be a remote git
   location, or it can simply be the path to a cloned tree inside your
   development machine.
#. As of Fedora 15, that ships with gcc 4.6.0, the compilation is more
   strict, so things such as an unused variable in the code \*will\*
   lead to a build failure. You can disable that level of strictness by
   providing *extra configure script options* to your qemu-kvm userspace
   build. Right below the ``user_git_repo line``, you can set the
   variable ``extra_configure_options`` to include ``--disable-werror``.
   Let's say you also want Avocado-VT to fetch from my local tree,
   ``/home/lmr/Code/qemu-kvm``, master branch, same for the
   kvm-unit-tests repo. If you make those changes, your build variant
   will look like:

   ::

                   - git:
                       mode = git
                       user_git_repo = /home/lmr/Code/qemu-kvm
                       extra_configure_options = --disable-werror
                       user_branch = master
                       user_lbranch = master
                       test_git_repo = /home/lmr/Code/kvm-unit-tests

#. Now you can just run Avocado-VT as usual, you just have to change
   the main control file (called ``control`` with the unittest one
   ``control.unittests``

   ::

       $ $HOME/Code/autotest/client/bin/autotest $HOME/Code/autotest/client/tests/kvm/control.unittests

#. The output of a typical unittest execution looks like. Notice that
   autotest informs you where the logs of each individual unittests are
   located, so you can check that out as well.

   ::

       07/14 18:49:44 INFO |  unittest:0052| Running apic
       07/14 18:49:44 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/apic.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S -cpu qemu64,+x2apic
       07/14 18:49:46 INFO |  unittest:0096| Waiting for unittest apic to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 18:59:46 ERROR|  unittest:0108| Exception happened during apic: Timeout elapsed (600s)
       07/14 18:59:46 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/apic.log
       07/14 18:59:46 INFO |  unittest:0052| Running smptest
       07/14 19:00:15 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:00:16 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/smptest.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:00:17 INFO |  unittest:0096| Waiting for unittest smptest to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:00:17 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:00:18 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/smptest.log
       07/14 19:00:18 INFO |  unittest:0052| Running smptest3
       07/14 19:00:18 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 3 -kernel '/usr/local/autotest/tests/kvm/unittests/smptest.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:00:19 INFO |  unittest:0096| Waiting for unittest smptest3 to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:00:19 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:00:20 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/smptest3.log
       07/14 19:00:20 INFO |  unittest:0052| Running vmexit
       07/14 19:00:20 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/vmexit.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:00:21 INFO |  unittest:0096| Waiting for unittest vmexit to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:00:31 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:00:31 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/vmexit.log
       07/14 19:00:31 INFO |  unittest:0052| Running access
       07/14 19:00:31 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/access.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:00:32 INFO |  unittest:0096| Waiting for unittest access to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:01:02 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:01:03 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/access.log
       07/14 19:01:03 INFO |  unittest:0052| Running emulator
       07/14 19:01:03 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/emulator.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:01:05 INFO |  unittest:0096| Waiting for unittest emulator to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:01:06 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:01:07 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/emulator.log
       07/14 19:01:07 INFO |  unittest:0052| Running hypercall
       07/14 19:01:07 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/hypercall.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:01:08 INFO |  unittest:0096| Waiting for unittest hypercall to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:01:08 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:01:09 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/hypercall.log
       07/14 19:01:09 INFO |  unittest:0052| Running idt_test
       07/14 19:01:09 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/idt_test.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:01:10 INFO |  unittest:0096| Waiting for unittest idt_test to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:01:10 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:01:11 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/idt_test.log
       07/14 19:01:11 INFO |  unittest:0052| Running msr
       07/14 19:01:11 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/msr.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:01:12 INFO |  unittest:0096| Waiting for unittest msr to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:01:13 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:01:13 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/msr.log
       07/14 19:01:13 INFO |  unittest:0052| Running port80
       07/14 19:01:13 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/port80.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:01:14 INFO |  unittest:0096| Waiting for unittest port80 to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:01:31 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:01:32 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/port80.log
       07/14 19:01:32 INFO |  unittest:0052| Running realmode
       07/14 19:01:32 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/realmode.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:01:33 INFO |  unittest:0096| Waiting for unittest realmode to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:01:33 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:01:34 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/realmode.log
       07/14 19:01:34 INFO |  unittest:0052| Running sieve
       07/14 19:01:34 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/sieve.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:01:35 INFO |  unittest:0096| Waiting for unittest sieve to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:02:05 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:02:05 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/sieve.log
       07/14 19:02:05 INFO |  unittest:0052| Running tsc
       07/14 19:02:05 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/tsc.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:02:06 INFO |  unittest:0096| Waiting for unittest tsc to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:02:06 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:02:07 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/tsc.log
       07/14 19:02:07 INFO |  unittest:0052| Running xsave
       07/14 19:02:07 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/xsave.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:02:08 INFO |  unittest:0096| Waiting for unittest xsave to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:02:09 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:02:09 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/xsave.log
       07/14 19:02:09 INFO |  unittest:0052| Running rmap_chain
       07/14 19:02:09 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/rmap_chain.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S
       07/14 19:02:11 INFO |  unittest:0096| Waiting for unittest rmap_chain to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:02:12 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:02:13 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/rmap_chain.log
       07/14 19:02:13 INFO |  unittest:0052| Running svm
       07/14 19:02:13 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/svm.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S -enable-nesting -cpu qemu64,+svm
       07/14 19:02:13 INFO |   aexpect:0783| (qemu) qemu: -enable-nesting: invalid option
       07/14 19:02:13 INFO |   aexpect:0783| (qemu) (Process terminated with status 1)
       07/14 19:02:13 ERROR|  unittest:0108| Exception happened during svm: VM creation command failed:    "/usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/svm.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S -enable-nesting -cpu qemu64,+svm"    (status: 1,    output: 'qemu: -enable-nesting: invalid option\n')
       07/14 19:02:13 ERROR|  unittest:0115| Not possible to collect logs
       07/14 19:02:13 INFO |  unittest:0052| Running svm-disabled
       07/14 19:02:13 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/svm.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S -cpu qemu64,-svm
       07/14 19:02:14 INFO |  unittest:0096| Waiting for unittest svm-disabled to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:02:15 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:02:16 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/svm-disabled.log
       07/14 19:02:16 INFO |  unittest:0052| Running kvmclock_test
       07/14 19:02:16 INFO |    kvm_vm:0782| Running qemu command:
       /usr/local/autotest/tests/kvm/qemu -name 'vm1' -nodefaults -vga std -monitor unix:'/tmp/monitor-humanmonitor1-20110714-184944-6ms0',server,nowait -qmp unix:'/tmp/monitor-qmpmonitor1-20110714-184944-6ms0',server,nowait -serial unix:'/tmp/serial-20110714-184944-6ms0',server,nowait -m 512 -smp 2 -kernel '/usr/local/autotest/tests/kvm/unittests/kvmclock_test.flat' -vnc :0 -chardev file,id=testlog,path=/tmp/testlog-20110714-184944-6ms0 -device testdev,chardev=testlog  -S --append "10000000 `date +%s`"
       07/14 19:02:17 INFO |  unittest:0096| Waiting for unittest kvmclock_test to complete, timeout 600, output in /tmp/testlog-20110714-184944-6ms0
       07/14 19:02:33 INFO |   aexpect:0783| (qemu) (Process terminated with status 0)
       07/14 19:02:34 INFO |  unittest:0113| Unit test log collected and available under /usr/local/autotest/results/default/kvm.qemu-kvm-git.unittests/debug/kvmclock_test.log
       07/14 19:02:34 ERROR|       kvm:0094| Test failed: TestFail: Unit tests failed: apic svm

You might take a look at the ``unittests.cfg`` config file options to do
some tweaking you might like, such as making the timeout to consider a
unittest as failed smaller and other things.

