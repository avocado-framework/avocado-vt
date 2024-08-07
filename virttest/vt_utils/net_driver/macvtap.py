# Library for the macvtap address related functions.
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
import os

from avocado.utils import process

from virttest import arch, utils_misc
from virttest.vt_utils.net import interface as iface


def create_macvtap(iface=None, tapname=None, mode="vepa", mac_addr=None):
    """
    Create a Macvtap device.

    :param iface: The physical interface.
    :type iface: String.
    :param tapname: The macvtap name.
    :type tapname: String.
    :param mode:  The macvtap type mode (vepa, bridge, private)
    :type mode: String.
    :param mac_addr: The macvtap mac address.
    :type mac_addr: String.

    :raise: A RuntimeError may be raised if running command fails.
    """
    if not iface:
        iface = get_macvtap_base_iface(iface)
    if not tapname:
        tapname = "macvtap" + utils_misc.generate_random_id()
    cmd = "ip link add link %s name %s type %s" % (iface, tapname, mode)
    process.run(cmd, shell=True)
    if mac_addr:
        cmd = "ip link set %s address %s up" % (tapname, mac_addr)
        process.run(cmd, shell=True)


def show_macvtap(tapname):
    """
    Show the macvtap details.

    :param tapname: The macvtap name.
    :type tapname: String.

    :return: The macvtap details.
    :rtype: String.
    """
    cmd = "ip link show %s" % tapname
    cmd_obj = process.run(cmd, shell=True)
    return cmd_obj.stdout_text.strip()


def delete_macvtap(tapname):
    """
    Delete the macvtap.

    :param tapname: The macvtap name.
    :type tapname: String.
    """
    cmd = "ip link delete %s" % tapname
    process.run(cmd, shell=True)


def get_macvtap_base_iface(base_interface=None):
    """
    Get physical interface to create macvtap, if you assigned base interface
    is valid(not belong to any bridge and is up), will use it; else use the
    first physical interface,  which is not a brport and up.
    """
    tap_base_device = None

    (dev_int, _) = iface.get_sorted_net_if()

    if base_interface and base_interface in dev_int:
        if (not iface.net_if_is_brport(base_interface)) and (
            iface.is_iface_flag_same(base_interface, arch.IFF_UP)
        ):
            tap_base_device = base_interface

    if not tap_base_device:
        for interface in dev_int:
            if iface.net_if_is_brport(interface):
                continue
            if iface.is_iface_flag_same(interface, arch.IFF_UP):
                tap_base_device = interface
                break

    return tap_base_device


def open_macvtap(macvtap, queues=1):
    """
    Open a macvtap device and returns its file descriptors which are used by
    fds=<fd1:fd2:..> parameter of qemu.

    For single queue, only returns one file descriptor, it's used by
    fd=<fd> legacy parameter of qemu.

    If you not have a switch support vepa in you env, run this type case you
    need at least two nic on you host [just workaround].

    :param macvtap:  The macvtap name.
    :type macvtap: String.
    :param queues: Queue number.
    :type queues: Integer.

    :return: The file descriptors which are used
             by fds=<fd1:fd2:..> parameter of qemu.
    :rtype: String.
    """
    tapfds = []
    macvtap = "/dev/%s" % macvtap
    for queue in range(int(queues)):
        tapfds.append(str(os.open(macvtap, os.O_RDWR)))
    return ":".join(tapfds)
