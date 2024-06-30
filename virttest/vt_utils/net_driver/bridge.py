# Library for the bridge address related functions.
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
import json

from avocado.utils import process

from virttest.vt_utils.net import interface


def find_bridge_name(iface):
    """
    Finds bridge name based in the interface name.

    :param iface: The interface name.
    :type iface: String.

    :return: The bridge name. If not found, return None.
    :rtype: String or None.
    """
    cmd = "bridge -json link"
    cmd_obj = process.run(cmd, shell=True)
    output = cmd_obj.stdout_text.strip()
    bridge_info = json.loads(output)
    for bridge in bridge_info:
        if bridge["ifname"] in (iface,):
            return bridge["master"]
    return None


def add_to_bridge(ifname, brname):
    """
    Add the interface into the bridge.

    :param ifname: The interface name.
    :type ifname: String.

    :param brname: The bridge name.
    :type brname: String.
    """
    # To add an interface into the bridge, its state must be up.
    interface.bring_up_ifname(ifname)
    cmd_add_to_bridge = "ip link set %s master %s" % (ifname, brname)
    process.run(cmd_add_to_bridge, shell=True)


def del_from_bridge(ifname):
    """
    Delete the interface from the bridge.
    NOTE: Bringing the interface down is excluded at this function.
          You may call the function about bringing interface down after del_from_bridge().

    :param ifname: The interface name.
    :type ifname: String.
    """
    cmd = "ip link set %s nomaster" % ifname
    process.run(cmd, shell=True)
