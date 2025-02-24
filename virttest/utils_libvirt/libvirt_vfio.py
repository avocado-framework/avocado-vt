"""
Libvirt vfio related utilities.

:copyright: 2021 Red Hat Inc.
"""

import logging

from avocado.core import exceptions
from avocado.utils import process

LOG = logging.getLogger("avocado." + __name__)


def check_vfio_pci(pci_id, status_error=False, ignore_error=False, exp_driver=None):
    """
    Check if the driver is vfio-pci

    :param pci_id: The id of pci device
    :param status_error: Whether the driver should be vfio-pci
    :param ignore_error: Whether to raise an exception
    :param exp_driver: The expected driver
    :raise: TestFail if not match
    :return: True if got the expected driver;
        False otherwise when ignore_error is set to True
    """
    cmd = (
        "readlink -f /sys/bus/pci/devices/%s/driver "
        "| awk -F '/' '{print $NF}'" % pci_id
    )
    output = process.run(cmd, shell=True, verbose=True).stdout_text.strip()
    res = (
        exp_driver == output
        if exp_driver
        else output.endswith(("vfio-pci", "vfio_pci"))
    )
    if res == status_error:
        err_msg = "Get incorrect driver {}, it should{} be {}.".format(
            output,
            " not" if status_error else "",
            exp_driver if exp_driver else "vfio-pci",
        )
        if ignore_error:
            LOG.error(err_msg)
            return False
        else:
            raise exceptions.TestFail(err_msg)
    else:
        return True
