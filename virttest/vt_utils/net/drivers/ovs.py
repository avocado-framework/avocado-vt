# Library for the openvswitch related functions.
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
from avocado.utils import process


def ovs_br_exists(brname):
    """
    Check if bridge exists or not.

    :param brname: Name of the bridge.
    :type brname: String.

    :return: True if found, otherwise, return False.
    :rtype: Boolean.

    :raise: RuntimeError if executing command fails.
    """
    cmd = "ovs-vsctl br-exists %s" % brname
    cmd_obj = process.run(cmd, shell=True)
    status = cmd_obj.exit_status
    if status != 0:
        return False
    return True


def add_ovs_bridge(brname):
    """
    Add a bridge.

    :param brname: Name of the bridge.
    :type brname: String.

    :raise: RuntimeError if executing command fails.
    """
    cmd = "ovs-vsctl --may-exist add-br %s" % brname
    process.run(cmd, shell=True)


def del_ovs_bridge(brname):
    """
    Delete a bridge from ovs.

    :param brname: Name of the bridge.
    :type brname: String.

    :raise: RuntimeError if executing command fails.
    """
    cmd = "ovs-vsctl --if-exists del-br %s" % brname
    process.run(cmd, shell=True)
