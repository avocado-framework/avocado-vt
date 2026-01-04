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

from virttest.vt_cluster import cluster

from ..port_resource import PortResource

LOG = logging.getLogger("avocado." + __name__)


class TapPort(PortResource):
    """
    The tap port.
    """

    PORT_TYPE = "tap"

    def bind_backings(self, nodes):
        """
        Bind the resource to a backing on a worker node.
        """
        node = nodes[0]
        if not node:
            raise ValueError("No worker node is set to bind to")

        r, o = node.proxy.resource.create_backing_object(
            self.get_backing_config(node.name)
        )
        if r != 0:
            raise Exception(o["out"])
        self._update_binding(node, o["out"]["backing"])

    def unbind_backings(self, nodes):
        """
        Unbind the resource from a worker node.
        """
        node, backing_id = self.get_binding(nodes[0])
        r, o = node.proxy.resource.destroy_backing_object(backing_id)
        if r != 0:
            raise Exception(o["out"])
        self._update_binding(node, None)

    def sync(self, arguments, node=None):
        LOG.debug("Sync up the configuration of the tap port")
        node, backing_id = self.get_binding(node)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id,
            "sync",
            arguments,
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.meta["allocated"] = config["meta"]["allocated"]
        self.spec.update(
            {
                "switch": config["spec"]["switch"],
                "fds": config["spec"]["fds"],
                "ifname": config["spec"]["ifname"],
            }
        )

    def allocate(self, arguments, node=None):
        node, backing_id = self.get_binding(node)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id,
            "allocate",
            arguments,
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.meta["allocated"] = config["meta"]["allocated"]
        self.spec.update(
            {
                "switch": config["spec"]["switch"],
                "fds": config["spec"]["fds"],
                "ifname": config["spec"]["ifname"],
            }
        )

    def release(self, arguments, node=None):
        node, backing_id = self.get_binding(node)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id,
            "release",
            arguments,
        )
        if r != 0:
            raise Exception(o["out"])

        self.meta["allocated"] = False
        self.spec.update(
            {
                "switch": None,
                "fds": None,
                "ifname": None,
            }
        )
