#
# Library for pci device related helper functions
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; specifically version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat (c) 2024 and Avocado contributors
# Author: Houqi Zuo <hzuo@redhat.com>
import re

from avocado.utils import process


def get_full_pci_id(pci_id):
    """
    Get full PCI ID of pci_id.

    :param pci_id: PCI ID of a device.
    :type pci_id: String

    :return: A full PCI ID. If exception happens, return None
    :rtype: String
    """
    cmd = "lspci -D | awk '/%s/ {print $1}'" % pci_id
    try:
        return process.run(cmd, shell=True).stdout_text.strip()
    except process.CmdError:
        return None


def get_pci_id_using_filter(pci_filter):
    """
    Get PCI ID from pci filter in host.

    :param pci_filter: PCI filter regex of a device (adapter name)
    :type pci_filter: string

    :return: list of pci ids with adapter name regex
    :rtype: List
    """
    cmd = "lspci | grep -F '%s' | awk '{print $1}'" % pci_filter
    cmd_obj = process.run(cmd, shell=True)
    status, output = cmd_obj.exit_status, cmd_obj.stdout_text.strip()
    if status != 0 or not output:
        return []
    return output.split()


def get_interface_from_pci_id(pci_id, nic_regex=""):
    """
    Get interface from pci id in host.

    :param pci_id: PCI id of the interface to be identified.
    :type pci_id: String
    :param nic_regex: regex to match nic interfaces.
    :type nic_regex: String

    :return: interface name associated with the pci id.
    :rtype: String
    """
    if not nic_regex:
        nic_regex = "\w+(?=: flags)|\w+(?=\s*Link)"
    cmd = "ifconfig -a"
    cmd_obj = process.run(cmd, shell=True)
    status, output = cmd_obj.exit_status, cmd_obj.stdout_text.strip()
    if status != 0:
        return None
    ethnames = re.findall(nic_regex, output)
    for each_interface in ethnames:
        cmd = "ethtool -i %s | awk '/bus-info/ {print $2}'" % each_interface
        cmd_obj = process.run(cmd, shell=True)
        status, output = cmd_obj.exit_status, cmd_obj.stdout_text.strip()
        if status:
            continue
        if pci_id in output:
            return each_interface
    return None


def get_vendor_from_pci_id(pci_id):
    """
    Check out the device vendor ID according to pci_id.

    :param pci_id: PCI ID of a device.
    :type pci_id: String

    :return: The device vendor ID.
    :rtype: String
    """
    cmd = "lspci -n | awk '/%s/ {print $3}'" % pci_id
    return re.sub(
        ":", " ", process.run(cmd, shell=True, ignore_status=True).stdout_text
    )
