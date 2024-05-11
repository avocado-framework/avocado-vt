# Library for the tap device related functions.
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
import fcntl
import os
import struct

from virttest import arch
from virttest.vt_utils.net import interface


def open_tap(devname, ifname, queues=1, vnet_hdr=True):
    """
    Open a tap device and returns its file descriptors which are used by
    fds=<fd1:fd2:..> parameter of qemu.

    For single queue, only returns one file descriptor, it's used by
    fd=<fd> legacy parameter of qemu.

    :param devname: TUN device path.
    :type devname: String.
    :param ifname: TAP interface name.
    :type ifname: String.
    :param queues: Queue number.
    :type queues: Integer.
    :param vnet_hdr: Whether enable the vnet header.
    :type vnet_hdr: Boolean.

    :return: The file descriptors which are used by fds=<fd1:fd2:..> parameter
             of qemu.
    :rtype: String.
    """
    tapfds = []

    for i in range(int(queues)):
        tapfds.append(str(os.open(devname, os.O_RDWR)))

        flags = arch.IFF_TAP | arch.IFF_NO_PI

        if interface.vnet_support_probe(int(tapfds[i]), "IFF_MULTI_QUEUE"):
            flags |= arch.IFF_MULTI_QUEUE

        if vnet_hdr and interface.vnet_support_probe(int(tapfds[i]), "IFF_VNET_HDR"):
            flags |= arch.IFF_VNET_HDR

        ifr = struct.pack("16sh", ifname.encode(), flags)
        fcntl.ioctl(int(tapfds[i]), arch.TUNSETIFF, ifr)

    return ":".join(tapfds)
