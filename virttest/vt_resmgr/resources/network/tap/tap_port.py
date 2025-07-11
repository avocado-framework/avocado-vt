import logging

from virttest.vt_cluster import cluster

from ..port_resource import _PortResource

LOG = logging.getLogger("avocado." + __name__)


class _TapPort(_PortResource):
    """
    The tap port.
    """

    def __init__(self, resource_config):
        super().__init__(resource_config)
        self.resource_spec["switch"] = dict()
        self.resource_spec["fds"] = dict()
        self.resource_spec["ifname"] = dict()

    def bind(self, arguments):
        """
        Bind the resource to a backing on a worker node.
        """
        nodes = arguments.pop("nodes", list(self.resource_bindings.keys()))
        for node_name in nodes:
            if not self.resource_bindings.get(node_name):
                LOG.info(f"Bind the tap port {self.resource_id} to node {node_name}")
                node = cluster.get_node(node_name)
                r, o = node.proxy.resource.create_backing_object(self.resource_config)
                if r != 0:
                    raise Exception(o["out"])
                self.resource_bindings[node_name] = o["out"]
            else:
                LOG.info(f"The tap port {self.resource_id} has already bound to {node_name}")

    def unbind(self, arguments):
        """
        Unbind the tap port from a worker node
        """
        nodes = arguments.pop("nodes", list(self.resource_bindings.keys()))
        for node_name in nodes:
            backing_id = self.resource_bindings.get(node_name)
            if backing_id:
                LOG.info(f"Unbind the tap port {self.resource_id} from node {node_name}")
                node = cluster.get_node(node_name)
                r, o = node.proxy.resource.destroy_backing_object(backing_id)
                if r != 0:
                    raise Exception(o["out"])
                self.resource_bindings[node_name] = None
            else:
                LOG.info(f"The tap port {self.resource_id} has already unbound from {node_name}")

    def sync(self, arguments):
        LOG.debug(f"Sync up the configuration of the tap port {self.resource_id}")
        node_name = arguments.get("node_name")
        if not node_name:
            node_name, backing_id = list(self.resource_bindings.items())[0]
        else:
            backing_id = self.resource_bindings[node_name]
        node = cluster.get_node(node_name)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, {"sync": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.resource_meta["allocated"] = config["meta"]["allocated"] | self.resource_meta["allocated"]
        self.resource_spec["switch"].update({backing_id: config["spec"]["switch"]})
        self.resource_spec["fds"].update({backing_id: config["spec"]["fds"]})
        self.resource_spec["ifname"].update({backing_id: config["spec"]["ifname"]})

    def allocate(self, arguments):
        node_name = arguments.get("node_name")
        if not node_name:
            node_name, backing_id = list(self.resource_bindings.items())[0]
        else:
            backing_id = self.resource_bindings[node_name]
        LOG.debug(f"Allocate the tap port {self.resource_id} from {node_name}.")
        node = cluster.get_node(node_name)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, {"allocate": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.resource_meta["allocated"] = config["meta"]["allocated"] | self.resource_meta["allocated"]
        self.resource_spec["switch"].update({backing_id: config["spec"]["switch"]})
        self.resource_spec["fds"].update({backing_id: config["spec"]["fds"]})
        self.resource_spec["ifname"].update({backing_id: config["spec"]["ifname"]})

    def release(self, arguments):
        node_name = arguments.get("node_name")
        if not node_name:
            node_name, backing_id = list(self.resource_bindings.items())[0]
        else:
            backing_id = self.resource_bindings[node_name]
        node = cluster.get_node(node_name)
        LOG.debug(f"Release the tap port {self.resource_id} from {node_name}")
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, {"release": arguments}
        )
        if r != 0:
            raise Exception(o["out"])
        self.resource_meta["allocated"] = False | self.resource_meta["allocated"]
        self.resource_spec["switch"].update({backing_id: None})
        self.resource_spec["fds"].update({backing_id: None})
        self.resource_spec["ifname"].update({backing_id: None})


def get_port_resource_class(resource_type):
    mapping = {
        "port": _TapPort,
    }

    return mapping.get(resource_type)
