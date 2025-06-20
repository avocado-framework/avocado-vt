import logging

from virttest.utils_numeric import normalize_data_size
from virttest.vt_cluster import cluster

from ..volume import _FileVolume

LOG = logging.getLogger("avocado." + __name__)


class _NfsFileVolume(_FileVolume):
    """
    The nfs file-based volume
    """

    def bind(self, arguments):
        """
        Bind the resource to a backing on a worker node.
        Note: A nfs volume resource can have many bindings
        """
        nodes = arguments.pop("nodes", list(self.resource_bindings.keys()))
        for node_name in nodes:
            if not self.resource_bindings.get(node_name):
                LOG.info(f"Bind the nfs volume {self.resource_id} to node {node_name}")
                node = cluster.get_node(node_name)
                r, o = node.proxy.resource.create_backing_object(self.resource_config)
                if r != 0:
                    raise Exception(o["out"])
                self.resource_bindings[node_name] = o["out"]
            else:
                LOG.info(
                    f"The nfs volume {self.resource_id} has already bound to {node_name}"
                )

    def unbind(self, arguments):
        """
        Unbind the nfs volume from a worker node
        """
        nodes = arguments.pop("nodes", list(self.resource_bindings.keys()))
        for node_name in nodes:
            backing_id = self.resource_bindings.get(node_name)
            if backing_id:
                LOG.info(
                    f"Unbind the nfs volume {self.resource_id} from node {node_name}"
                )
                node = cluster.get_node(node_name)
                r, o = node.proxy.resource.destroy_backing_object(backing_id)
                if r != 0:
                    raise Exception(o["out"])
                self.resource_bindings[node_name] = None
            else:
                LOG.info(
                    f"The nfs volume {self.resource_id} has already unbound from {node_name}"
                )

    def sync(self, arguments):
        LOG.debug(f"Sync up the configuration of the nfs volume {self.resource_id}")
        node_name, backing_id = list(self.resource_bindings.items())[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, {"sync": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.resource_meta["allocated"] = config["meta"]["allocated"]
        self.resource_spec["uri"] = config["spec"]["uri"]
        self.resource_spec["allocation"] = config["spec"]["allocation"]

    def allocate(self, arguments):
        node_name, backing_id = list(self.resource_bindings.items())[0]
        node = cluster.get_node(node_name)

        LOG.debug(f"Allocate the nfs volume {self.resource_id} from {node_name}.")
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, {"allocate": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.resource_meta["allocated"] = config["meta"]["allocated"]
        self.resource_spec["uri"] = config["spec"]["uri"]
        self.resource_spec["allocation"] = config["spec"]["allocation"]

    def release(self, arguments):
        LOG.debug(f"Release the nfs volume {self.resource_id} from {node_name}")
        node_name, backing_id = list(self.resource_bindings.items())[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, {"release": arguments}
        )
        if r != 0:
            raise Exception(o["out"])
        self.resource_meta["allocated"] = False
        self.resource_spec["allocation"] = 0
        self.resource_spec["uri"] = None

    def resize(self, arguments):
        """
        Resize the nfs volume
        """
        new = int(normalize_data_size(arguments["size"], "B"))
        if new != self.resource_spec["size"]:
            LOG.debug(f"Resize the nfs volume {self.resource_id} from {node_name}")
            node_name, backing_id = list(self.resource_bindings.items())[0]
            node = cluster.get_node(node_name)
            r, o = node.proxy.resource.update_resource_by_backing(
                backing_id, {"resize": arguments}
            )
            if r != 0:
                raise Exception(o["out"])
            self.resource_spec["size"] = new
        else:
            LOG.debug(f"New size {new} is the same with the original")


def get_nfs_resource_class(resource_type):
    mapping = {
        "volume": _NfsFileVolume,
    }

    return mapping.get(resource_type)
