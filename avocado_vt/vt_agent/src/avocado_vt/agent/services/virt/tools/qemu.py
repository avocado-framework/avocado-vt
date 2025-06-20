# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>


import logging
import os
import re

from avocado_vt.agent.core import data_dir
from virttest import utils_qemu
from virttest.arch import ARCH
from virttest.vt_utils import qemu_utils

from avocado.utils import aurl
from avocado.utils import path as utils_path
from avocado.utils import process

LOG = logging.getLogger("avocado.service." + __name__)


def _get_path(base_path, user_path):
    """
    Translate a user specified path to a real path.
    If user_path is relative, append it to base_path.
    If user_path is absolute, return it as is.

    :param base_path: The base path of relative user specified paths.
    :param user_path: The user specified path.
    """
    if aurl.is_url(user_path):
        return user_path
    if not os.path.isabs(user_path):
        user_path = os.path.join(base_path, user_path)
        user_path = os.path.abspath(user_path)
    return os.path.realpath(user_path)


def _get_backend_dir():
    """
    Get the appropriate backend directory. Example: backends/qemu.
    """
    return os.path.join(data_dir.get_root_dir(), "backends", "qemu")


def get_qemu_binary(qemu_path):
    """
    Get the path to the qemu binary currently in use.
    """
    # Update LD_LIBRARY_PATH for built libraries (libspice-server)
    qemu_binary_path = _get_path(_get_backend_dir(), qemu_path)

    if not os.path.isfile(qemu_binary_path):
        LOG.debug(
            "Could not find params qemu in %s, searching the "
            "host PATH for one to use",
            qemu_binary_path,
        )
        QEMU_BIN_NAMES = [
            "qemu-kvm",
            "qemu-system-%s" % (ARCH),
            "qemu-system-ppc64",
            "qemu-system-x86",
            "qemu_system",
            "kvm",
        ]
        for qemu_bin in QEMU_BIN_NAMES:
            try:
                qemu_binary = utils_path.find_command(qemu_bin)
                LOG.debug("Found %s", qemu_binary)
                break
            except utils_path.CmdNotFoundError:
                continue
        else:
            raise OSError(
                "qemu binary names %s not found in " "system" % " ".join(QEMU_BIN_NAMES)
            )
    else:
        qemu_binary = qemu_binary_path
    return qemu_binary


def get_machines_info(qemu_binary):
    """
    Return all machines information supported by qemu

    :param qemu_binary: Path to qemu binary
    :return: A dict of all machines
    """
    return utils_qemu.get_machines_info(qemu_binary)


def has_option(option, qemu_binary="qemu"):
    """Check if a specific QEMU option is available.

    :param option: The QEMU option to check.
    :param qemu_binary: The path to the QEMU binary. Defaults to "qemu".
    :return: True if the option is available, False otherwise.
    """
    qemu_path = get_qemu_binary(qemu_binary)
    return qemu_utils.has_option(option, qemu_path)


def has_device(device, qemu_binary="qemu"):
    """Check if a specific QEMU device is available.

    :param device: The QEMU device to check.
    :param qemu_binary: The path to the QEMU binary. Defaults to "qemu".
    :return: True if the device is available, False otherwise.
    """
    qemu_path = get_qemu_binary(qemu_binary)
    cmd = "%s -device \? 2>&1" % qemu_path
    hlp = process.run(cmd, shell=True, ignore_status=True, verbose=False).stdout_text
    return bool(
        re.search(r'name "%s"|alias "%s"' % (device, device), hlp, re.MULTILINE)
    )


def has_object(obj, qemu_binary="qemu"):
    """Check if a specific QEMU object is available.

    :param obj: The QEMU object to check.
    :param qemu_binary: The path to the QEMU binary. Defaults to "qemu".
    :return: True if the object is available, False otherwise.
    """
    qemu_path = get_qemu_binary(qemu_binary)
    cmd = "%s -object \? 2>&1" % qemu_path
    hlp = process.run(cmd, shell=True, ignore_status=True, verbose=False).stdout_text
    return bool(re.search(r"^\s*%s\n" % obj, hlp, re.MULTILINE))


def is_pci_device(device, qemu_binary="qemu"):
    """Check if a specific QEMU device is a PCI device.

    :param device: The QEMU device to check.
    :param qemu_binary: The path to the QEMU binary. Defaults to "qemu".
    :return: True if the device is a PCI device, False otherwise.
    """
    qemu_path = get_qemu_binary(qemu_binary)
    cmd = "%s -device \? 2>&1" % qemu_path
    hlp = process.run(cmd, shell=True, ignore_status=True, verbose=False).stdout_text
    return bool(
        re.search(
            r'name "%s", bus PCI|bus PCI, .*alias "%s"' % (device, device),
            hlp,
            re.MULTILINE,
        )
    )


def get_version(qemu_binary="qemu"):
    """Get the version of the specified QEMU binary.

    :param qemu_binary: The path to the QEMU binary. Defaults to "qemu".
    :return: The version of the QEMU binary.
    """
    qemu_path = get_qemu_binary(qemu_binary)
    return utils_qemu.get_qemu_version(qemu_path)


def get_help_info(option=None, qemu_binary="qemu"):
    qemu_path = get_qemu_binary(qemu_binary)
    if option:
        cmd = f"{qemu_path} {option}help 2>&1"
    else:
        cmd = f"{qemu_path} -help 2>&1"
    hlp = process.run(cmd, shell=True, ignore_status=True, verbose=False).stdout_text
    return hlp
