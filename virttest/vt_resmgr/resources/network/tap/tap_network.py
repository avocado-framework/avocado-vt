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
                "export": pool_params.get("export"),
            }
        )
        return config

    def customize_pool_config(self, node_name):
        config = copy.deepcopy(self.config)
        config["spec"]["switch"] = config["spec"]["switch"][node_name]["ifname"]
        config["spec"]["export"] = config["spec"]["export"][node_name]["ifname"]
        return config

    def meet_conditions(self, condition_params):
        """
        Check if the pool can meet the conditions
        """
        selectors = condition_params.get("port_pool_selectors", list())
        if not selectors:
            # Add the network pool type
            network_type = condition_params.get("network_type")
            if network_type:
                selectors.append(
                    {
                        "key": "type",
                        "operator": "==",
                        "values": network_type,
                    }
                )

        return PoolSelector(str(selectors)).match(self)
