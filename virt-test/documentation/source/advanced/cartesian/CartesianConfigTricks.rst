=======================
Cartesian Config Tricks
=======================

Changing test order
===================

The Cartesian Config system implemented in virt-test does have some limitations -
for example, the order of tests is dependent on the order on which each variant
is defined on the config files, making executing tests on a different order a
daunting prospect.

In order to help people with this fairly common use case, we'll demonstrate how
to use some of the cartesian config features to accomplish executing your tests
in the order you need. In this example, we're going to execute the `unix` migration
mode tests before the `tcp` one. In the actual cartesian config file, `tcp` is always
going to be executed before `unix` on a normal virt-test execution.

Create a custom config
----------------------

For the sake of simplicity, we'll create the file under `backends/qemu/cfg/custom.cfg`::

    $ touch backends/qemu/cfg/custom.cfg

Then, let's add the following text to it (please keep in mind that our maintainers
are constantly adding new variants to the base virt-test config, so you might need
to tweak the contents to match the current state of the config)::

    include tests-shared.cfg

    variants:
        - @custom_base:
            only JeOS.20
            only i440fx
            only smp2
            only qcow2
            only virtio_net
            only virtio_blk
            no hugepages
            no 9p_export
            no gluster
            no pf_assignable
            no vf_assignable
            no rng_random
            no rng_egd
            variants:
                - @custom_1:
                    only migrate.default.unix
                - @custom_2:
                    only migrate.default.tcp

There you go. Note that you are not obligated to use `@` at your variant names, it's
just for the sake of not polluting the tag namespace too much. Now, let's test to
see if this config file is generating us just the 2 tests we actually want::

    $ virttest/cartesian_config.py backends/qemu/cfg/custom.cfg
    dict    1:  qcow2.virtio_blk.smp2.virtio_net.JeOS.20.x86_64.io-github-autotest-qemu.migrate.unix
    dict    2:  qcow2.virtio_blk.smp2.virtio_net.JeOS.20.x86_64.io-github-autotest-qemu.migrate.tcp

There you go. Now, you can simply execute this command line with::

    ./run -t qemu -c backends/qemu/cfg/custom.cfg

And then you'll see your tests executed in the correct order::

    $ ./run -t qemu -c backends/qemu/cfg/custom.cfg
    SETUP: PASS (2.31 s)
    DATA DIR: /home/user/virt_test
    DEBUG LOG: /home/user/Code/virt-test.git/logs/run-2014-12-19-12.12.29/debug.log
    TESTS: 2
    (1/2) qcow2.virtio_blk.smp2.virtio_net.JeOS.20.x86_64.io-github-autotest-qemu.migrate.unix: PASS (31.05 s)
    (2/2) qcow2.virtio_blk.smp2.virtio_net.JeOS.20.x86_64.io-github-autotest-qemu.migrate.tcp: PASS (22.10 s)
    TOTAL TIME: 53.25 s
    TESTS PASSED: 2
    TESTS FAILED: 0
    SUCCESS RATE: 100.00 %

This is the base idea - you can extend and filter variants on a cartesian config set as
much as you'd like, and tailor it to your needs.
