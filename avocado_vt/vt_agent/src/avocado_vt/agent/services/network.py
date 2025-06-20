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
import math
import os
import socket

from virttest import utils_misc, utils_net, utils_vsock

from avocado.utils.network import ports

LOG = logging.getLogger("avocado.service." + __name__)


def find_free_ports(
    start_port,
    end_port,
    count,
    address="localhost",
    sequent=False,
    family=socket.AF_INET,
    protocol=socket.SOCK_STREAM,
):
    """
    Find free ports in the specified range.

    :param start_port: start port
    :param end_port: end port
    """
    LOG.debug("Finding the free ports in the specified range")
    return ports.find_free_ports(
        start_port, end_port, count, address, sequent, family, protocol
    )


def get_free_cid(start_cid):
    """
    Get free cid in the specified range

    :param start_cid: int
    :return: free cid
    """
    LOG.debug("Getting the free cid in the specified range")
    return utils_vsock.get_guest_cid(start_cid)


def setup_tap_bridge(net_type, ifname, net_dst, queues=1):
    LOG.debug("Setting up tap bridge")
    tapfds = []
    if net_type == "macvtap":
        LOG.error("Unsupported interface type: %s" % net_type)
    else:
        tapfds = utils_net.open_tap(
            "/dev/net/tun", ifname, queues=queues, vnet_hdr=True
        )
        LOG.debug("Adding NIC ifname %s to bridge %s", ifname, net_dst)
        if net_type == "bridge":
            utils_net.add_to_bridge(ifname, net_dst)
    utils_net.bring_up_ifname(ifname)
    return tapfds


def cleanup_tap_bridge(
    net_type, ifname=None, tapfds=None, vhostfds=None, net_dst=None, queues=1
):
    LOG.debug("Cleaning up tap bridge")
    try:
        if net_type == "macvtap":
            LOG.error("Unsupported interface type: %s" % net_type)
        else:
            LOG.debug("Removing NIC ifname %s from bridge %s", ifname, net_dst)
            if tapfds:
                for i in tapfds.split(":"):
                    os.close(int(i))
            if vhostfds:
                for i in vhostfds.split(":"):
                    os.close(int(i))
            if ifname:
                deletion_time = max(5, math.ceil(int(queues) / 8))
                if utils_misc.wait_for(
                    lambda: ifname not in utils_net.get_net_if(), deletion_time
                ):
                    br_mgr, br_name = utils_net.find_current_bridge(ifname)
                    if br_name == net_dst:
                        br_mgr.del_port(net_dst, ifname)
    except TypeError:
        pass


def get_interfaces():
    LOG.info("Getting interfaces")
    return utils_net.get_net_if()


def delete_port_from_bridege(netdst, ifname):
    LOG.debug("Deleting port from bridge")
    try:
        br_mgr, br_name = utils_net.find_current_bridge(ifname)
        if br_name == netdst:
            br_mgr.del_port(netdst, ifname)
    except TypeError:
        pass


def generate_mac_address():
    LOG.debug("Generating mac address")
    return utils_net.generate_mac_address_simple()


def verify_ip_address_ownership(ip, macs, timeout=60.0, devs=None):
    LOG.debug(f"Verifying if the ip address {ip} belongs to MACs {macs}")
    return utils_net.verify_ip_address_ownership(ip, macs, timeout, devs)
