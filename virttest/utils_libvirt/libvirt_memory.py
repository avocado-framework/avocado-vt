"""
Libvirt memory related utilities.

:copyright: 2022 Red Hat Inc.
"""

import logging

from avocado.core import exceptions
from avocado.utils import process

from virttest import utils_package
from virttest.staging import utils_memory

LOG = logging.getLogger("avocado." + __name__)


def comp_memlock(exp_memlock):
    """
    Compare the locked mem with the given value.

    :param exp_memlock: The expected locked mem value
    :raise: TestError if the actual locked mem is invalid
    :return: True on success
    """
    LOG.debug("Check if the memlock is %s.", exp_memlock)
    tmp_act_memlock = get_qemu_process_memlock_hard_limit()
    LOG.debug("Actual memlock is {}.".format(tmp_act_memlock))
    try:
        act_memlock = int(tmp_act_memlock)
    except ValueError as e:
        raise exceptions.TestError(e)
    return exp_memlock == act_memlock


def get_qemu_process_memlock_hard_limit():
    """
    Get qemu process memlock hard limit

    """
    cmd = "prlimit -p `pidof qemu-kvm` -l |awk '/MEMLOCK/ {print $7}'"
    return process.run(cmd, shell=True).stdout_text.strip()


def get_qemu_process_memlock_limit():
    """
    Get qemu process memlock limit

    :return: qemu process soft limit and hard limit value.
    """
    cmd = "prlimit -p `pidof qemu-kvm` -l |awk '/MEMLOCK/ {print $6,$7}'"
    stdout = process.run(cmd, shell=True).stdout_text.strip().split()

    return (stdout[0], stdout[1])


def normalize_mem_size(mem_size, mem_unit):
    """
    Normalize the mem size and convert it to bytes.

    :param mem_size: The mem size
    :param mem_unit: The mem size unit
    :return: Byte format size
    """
    try:
        mem_size = float(mem_size)
        mem_unit_idx = ["B", "K", "M", "G", "T"].index(mem_unit[0].upper())
    except ValueError as e:
        raise exceptions.TestError(e)

    return int(mem_size * 1024**mem_unit_idx)


def consume_vm_freememory(vm_session, consume_value=100000, repeat_times=1):
    """
    Verify the free memory of the vm can be consumed normally

    :param vm_session: vm session
    :param consume_value: consume value , default 100000
    :param repeat_times: consume memory times, default 1
    """
    vm_session.cmd_status("swapoff -a")
    free_mem = utils_memory.freememtotal(vm_session)
    if not utils_package.package_install("numactl", vm_session):
        raise exceptions.TestError(
            "Fail to install package 'numactl' which provides command 'memhog'"
        )
    cmd = "memhog -r%d %dk" % (repeat_times, (free_mem - consume_value))
    status, stdout = vm_session.cmd_status_output(cmd, timeout=60)
    return (status, stdout)
