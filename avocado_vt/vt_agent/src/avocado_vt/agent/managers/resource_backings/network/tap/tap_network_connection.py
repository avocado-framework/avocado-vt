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

from virttest.vt_utils.net import interface
from virttest.vt_utils.net.drivers import bridge

from ...pool_connection import ResourcePoolConnection


class TapNetworkConnection(ResourcePoolConnection):
    POOL_TYPE = "linux_bridge"

    def __init__(self, network_config):
        super().__init__(network_config)
        self._switch = network_config["spec"]["switch"]
        self._export = network_config["spec"]["export"]

    def open(self):
        pass

    def close(self):
        pass

    @property
    def connected(self):
        if_info = interface.net_get_iface_info(self._switch)
        if (
            if_info
            and len(if_info) > 0
            and if_info[0]["operstate"] in ("UP",)
            and (
                bridge.find_bridge_name(self._export) in (self._switch,)
                or self._export == ""
            )
        ):
            return True
        return False

    @property
    def switch(self):
        return self._switch

    @property
    def export(self):
        return self._export
