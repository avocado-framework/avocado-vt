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
        config = self.pool_config
        config["spec"]["switch"] = config["spec"]["switch"][node_name]["ifname"]
        config["spec"]["export"] = config["spec"]["export"][node_name]["ifname"]
        return config

    @classmethod
    def get_resource_class(cls, resource_type):
        return get_port_resource_class(resource_type)

    def meet_resource_request(self, resource_type, resource_params):
        if resource_type is not ("port",) or resource_params.get("nettype") not in (
            "bridge",
        ):
            return False

        if not self._check_nodes_access(resource_params):
            return False

        return True

    def _check_nodes_access(self, resource_params):
        # Note if you want the image is created from a specific pool or
        # the image is handled on a specific worker node, you should
        # specify its image_pool_name
        vm_node_tag = resource_params.get("vm_node")
        if vm_node_tag:
            # Check if the pool can be accessed by the vm node
            vm_node = cluster.get_node_by_tag(vm_node_tag)
            if vm_node.name not in self.attaching_nodes:
                return False
        else:
            # Check if the pool can be accessed by one of the partition nodes
            node_names = [node.name for node in cluster.partition.nodes]
            if not set(self.attaching_nodes).intersection(set(node_names)):
                return False

        return True
