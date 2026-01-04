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

import copy
import logging

from ...pool import ResourcePool
from ...pool_selector import PoolSelector
from .tap_port import TapPort

LOG = logging.getLogger("avocado." + __name__)


class LinuxBridgeNetwork(ResourcePool):
    TYPE = "linux_bridge"
    _SUPPORTED_RESOURCES = {
        "port": TapPort,
    }

    @classmethod
    def define_config(cls, pool_name, pool_params):
        config = super().define_config(pool_name, pool_params)
        config["spec"].update(
            {
                "switch": pool_params["switch"],
                "export": pool_params["export"],
            }
        )
        return config

    def customize_pool_config(self, node_name):
        config = copy.deepcopy(self.config)
        config["spec"]["switch"] = config["spec"]["switch"][node_name]["ifname"]
        config["spec"]["export"] = config["spec"]["export"][node_name]["ifname"]
        return config

    def meet_resource_request(self, resource_type, resource_params):
        """
        Check if the pool can meet the conditions
        """
        if not super().meet_resource_request(resource_type, resource_params):
            return False

        selectors_string = resource_params.get("port_pool_selectors", list())
        if not selectors_string:
            selectors = list()
            # Add the network pool type
            network_type = resource_params.get("network_type")
            if network_type:
                selectors.append(
                    {
                        "key": "type",
                        "operator": "==",
                        "values": network_type,
                    }
                )
            selectors_string = str(selectors)

        return PoolSelector(selectors_string).match(self.config)
