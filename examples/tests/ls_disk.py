"""
Shows all existing disk partitions.

This test requires test-provider to be qemu.

Try this test without config, than put ls_disk.cfg into $tests/cfg/ directory
and see the difference.
Additionally you might put ls_disk_v2.cfg into $tests/cfg/ directory and
execute ls_disk_v2 test (which also uses this script!) and watch for even
bigger differences.

:difficulty: advanced
:copyright: 2014 Red Hat Inc.
"""

import logging

LOG = logging.getLogger("avocado.vt.examples.lsdisk")


def run(test, params, env):
    """
    Logs guest's disk partitions

    :param test: QEMU test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment.
    """
    vm = env.get_vm(params["main_vm"])
    session = vm.wait_for_login()
    output = session.cmd_output("ls /dev/[hsv]d* -1")
    LOG.info("Guest disks are:\n%s", output)

    # Let's get some monitor data
    monitor = vm.monitor
    # Following two provides different output for HMP and QMP monitors
    # output = monitor.cmd("info block", debug=False)
    # output = monitor.info("block", debug=False)
    # Following command unifies the response no matter which monitor is used
    output = monitor.info_block(debug=False)
    LOG.info("info block:\n%s", output)
