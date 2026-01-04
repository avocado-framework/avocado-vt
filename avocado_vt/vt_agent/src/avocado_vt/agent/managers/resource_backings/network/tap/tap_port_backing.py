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
# Authors: Houqi (Nick) Zuo <hzuo@redhat.com>

import logging

# pylint: disable=E0611
from avocado_vt.agent.core.logger import DEFAULT_LOG_NAME
from virttest import utils_misc
from virttest.vt_utils.net import interface, tap
from virttest.vt_utils.net.drivers import bridge

from ..nic_port_backing import NicPortBacking

LOG = logging.getLogger(f"{DEFAULT_LOG_NAME}." + __name__)


class TapPortBacking(NicPortBacking):
    RESOURCE_POOL_TYPE = "linux_bridge"
    PORT_TYPE = "tap"

    def __init__(self, backing_config, network_connection):
        super().__init__(backing_config, network_connection)
        self.switch = network_connection.switch
        self.tap_fd = None
        self.tap_ifname = None

    def allocate_resource(self, network_connection, arguments=None):
        """
        Create a tap device and put this device in to network_connection.

        :params network_connection: the TapNetworkConnection object.
        :type network_connection: class TapNetworkConnection.
        :params arguments: the device's params
        :type arguments: dict.

        :return: the resource info.
        :rtype: dict.
        """
        if not self.tap_ifname:
            self.tap_ifname = "tap_" + utils_misc.generate_random_string(8)
        try:
            self.tap_fd = tap.open_tap("/dev/net/tun", self.tap_ifname, vnet_hdr=True)
            self.tap_fd = self.tap_fd.split(":")
            interface.bring_up_ifname(self.tap_ifname)
            bridge.add_to_bridge(self.tap_ifname, self.switch)
        except Exception:
            self.release_resource(network_connection)
            raise

        return self.sync_resource_info(network_connection)

    def release_resource(self, network_connection, arguments=None):
        if self.is_resource_allocated():
            bridge.del_from_bridge(self.tap_ifname)
            interface.bring_down_ifname(self.tap_ifname)
            self.tap_fd = None
            self.tap_ifname = None
        else:
            LOG.debug("The tap port is NOT allocated. Nothing to do.")

    def sync_resource_info(self, network_connection=None, arguments=None):
        return {
            "meta": {
                "port-type": self.PORT_TYPE,
                "allocated": self.is_resource_allocated(),
            },
            "spec": {
                "switch": self.switch,
                "fds": self.tap_fd,
                "ifname": self.tap_ifname,
            },
        }

    def is_resource_allocated(self, network_connection=None):
        if self.switch and self.tap_fd and self.tap_ifname:
            if self.switch in (bridge.find_bridge_name(self.tap_ifname),):
                return True
        return False
