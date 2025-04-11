"""
Simple hostname test (on guest)

:difficulty: simple
:copyright: 2014 Red Hat Inc.
"""

import logging

LOG = logging.getLogger("avocado.vt.examples.guest_hostname")


def run(test, params, env):
    """
    Logs guest's hostname.
    1) get VM
    2) login to VM
    3) execute command
    4) log the output

    :param test: QEMU test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment.
    """
    # 1) get VM with name defined by params "main_vm"
    vm = env.get_vm(params["main_vm"])
    # vm = env.get_all_vms()[0]    # Get list of defined vms

    # 2) login to VM
    session = vm.wait_for_login()

    # 3) execute hostname
    output = session.cmd_output("hostname")

    # 4) log the output
    LOG.info("The output of 'hostname' command from guest is '%s'", output)
