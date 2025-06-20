import copy
import logging

from virttest.vt_cluster import cluster

from ...pool import _ResourcePool
from .tap_port import get_port_resource_class

LOG = logging.getLogger("avocado." + __name__)


class _LinuxBridgeNetwork(_ResourcePool):
    _POOL_TYPE = "linux_bridge"

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
        config = copy.deepcopy(self.pool_config)
        config["spec"]["switch"] = self.pool_config["spec"]["switch"][node_name]["ifname"]
        config["spec"]["export"] = self.pool_config["spec"]["export"][node_name]["ifname"]
        return config

    @classmethod
    def get_resource_class(cls, resource_type):
        return get_port_resource_class(resource_type)

    def meet_resource_request(self, resource_type, resource_params):
        if (
            resource_type not in ("port",)
            or resource_params.get("nettype") is not self._POOL_TYPE
        ):
            return False

        if not self._check_nodes_access(resource_params):
            return False

        return True

    def _check_nodes_access(self, resource_params):
        vm_node_tag = resource_params.get("vm_node")
        if vm_node_tag:
            # Check if the pool can be accessed by the vm node
            vm_node = cluster.get_node_by_tag(vm_node_tag)
            if vm_node.name not in self.attaching_nodes:
                return False
        else:
            node_names = [node.name for node in cluster.partitions[0].nodes]
            if not set(self.attaching_nodes).intersection(set(node_names)):
                return False

        return True
