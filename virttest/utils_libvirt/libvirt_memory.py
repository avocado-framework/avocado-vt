"""
Libvirt memory related utilities.

:copyright: 2022 Red Hat Inc.
"""

import logging

from avocado.utils import process

LOG = logging.getLogger('avocado.' + __name__)


def get_qemu_process_memlock_hard_limit():
    """
    Get qemu process memlock hard limit

    """
    cmd = "prlimit -p `pidof qemu-kvm` -l |awk '/MEMLOCK/ {print $7}'"
    return process.run(cmd, shell=True).stdout_text.strip()
