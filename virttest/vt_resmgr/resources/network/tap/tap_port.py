import logging

from virttest.vt_cluster import cluster

from ..port_resource import PortResource

LOG = logging.getLogger("avocado." + __name__)


class TapPort(PortResource):
    """
    The tap port.
    """

    PORT_TYPE = "tap"

    def bind(self, arguments):
        """
        Bind the resource to a backing on a worker node.
        """
        nodes = arguments.pop("nodes", self.resource_binding_nodes)
        if not nodes:
            raise ValueError("No worker node is set to bind to")

        for node_name in nodes:
            if not self._get_backing(node_name):
                LOG.info(f"Bind the tap port {self.resource_id} to node {node_name}")
                node = cluster.get_node(node_name)
                r, o = node.proxy.resource.create_backing_object(self.resource_config)
                if r != 0:
                    raise Exception(o["out"])
                self._set_backing(node_name, o["out"])
            else:
                LOG.info(
                    f"The tap port {self.resource_id} has already bound to {node_name}"
                )

    def unbind(self, arguments):
        """
        Unbind the resource from a worker node.
        """
        nodes = arguments.pop("nodes", self.resource_binding_nodes)
        for node_name in nodes:
            backing_id = self._get_backing(node_name)
            if backing_id:
                LOG.info(
                    f"Unbind the tap port {self.resource_id} from node {node_name}"
                )
                node = cluster.get_node(node_name)
                r, o = node.proxy.resource.destroy_backing_object(backing_id)
                if r != 0:
                    raise Exception(o["out"])
                self._set_backing(node_name, None)
            else:
                LOG.info(
                    f"The tap port {self.resource_id} was not bound to {node_name}"
                )

    def sync(self, arguments, node=None):
        LOG.debug(f"Sync up the configuration of the tap port {self.resource_id}")
        node, backing_id = self._get_binding(node)
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
        node, backing_id = self._get_binding(node)
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
        node, backing_id = self._get_binding(node)
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
