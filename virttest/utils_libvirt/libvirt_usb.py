"""
Utility functions for usb devices

:copyright: 2022 Red Hat Inc.
"""

import logging

from avocado.core import exceptions
from avocado.utils import process

LOG = logging.getLogger("avocado." + __name__)


def get_usbs_lists_on_host():
    """
    This function gets usb devices located
    on host system as a list

    :return: usb devices in list
    """
    lsusb_output = process.run(
        "lsusb", timeout=10, ignore_status=True, verbose=False, shell=True
    )
    if lsusb_output.exit_status != 0:
        raise exceptions.TestError(
            "Failed to execute lsusb on host with output:{}".format(lsusb_output)
        )
    return (lsusb_output.stdout_text.strip()).splitlines()


def check_usb_disk_type_in_vm(session, partition):
    """
    Check if a disk partition is a usb disk in VM.

    :param session: a login session to VM
    :param partition: The disk partition in VM to be checked.
    :return: If the disk is a usb device, return True.
    """
    try:
        cmd = "ls -l /dev/disk/by-id/ | grep %s | grep -i usb" % partition
        status = session.cmd_status(cmd)
        return status == 0
    except Exception as err:
        LOG.error("Error happens when check if new disk is usb device: %s", str(err))
        return False
