import logging

from virttest.utils_numeric import normalize_data_size
from virttest.vt_cluster import cluster

from ..volume import _FileVolume

LOG = logging.getLogger("avocado." + __name__)


class _DirFileVolume(_FileVolume):
    """
    The directory file-based volume
    """

    def bind(self, arguments):
        """
        Bind the resource to a backing on a worker node.
        Note: A local dir resource has one and only one binding in the cluster
        """
        node_name, backing_id = list(self.resource_bindings.items())[0]
        if backing_id:
            LOG.warning(
                f"The dir volume {self.resource_id} has already bound to {node_name}"
            )
        else:
            nodes = arguments.pop("nodes", [node_name])
            LOG.info(f"Bind the dir volume {self.resource_id} to {nodes[0]}")
            node = cluster.get_node(nodes[0])
            r, o = node.proxy.resource.create_backing_object(self.resource_config)
            if r != 0:
                raise Exception(o["out"])
            self.resource_bindings[nodes[0]] = o["out"]

    def unbind(self, arguments):
        """
        Unbind the resource from a worker node.
        Note: A dir resource must be released before unbinding
              because it has only one binding
        """
        node_name, backing_id = list(self.resource_bindings.items())[0]
        LOG.info(f"Unbind the dir volume {self.resource_id} from {node_name}")
        node = cluster.get_node(node_name)
        r, o = node.proxy.resource.destroy_backing_object(backing_id)
        if r != 0:
            raise Exception(o["out"])
        self.resource_bindings[node_name] = None

    def sync(self, arguments):
        LOG.debug(f"Sync up the configuration of the dir volume {self.resource_id}")
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

        LOG.debug(f"Allocate the dir volume {self.resource_id} from {node_name}.")
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
        node_name, backing_id = list(self.resource_bindings.items())[0]
        node = cluster.get_node(node_name)
        LOG.debug(f"Release the dir volume {self.resource_id} from {node_name}")
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, {"release": arguments}
        )
        if r != 0:
            raise Exception(o["out"])
        self.resource_meta["allocated"] = False
        self.resource_spec["allocation"] = 0

    def resize(self, arguments):
        """
        Resize the local dir volume resource
        """
        new = int(normalize_data_size(arguments["size"], "B"))
        if new != self.resource_spec["size"]:
            node_name, backing_id = list(self.resource_bindings.items())[0]
            LOG.debug(f"Resize the dir volume {self.resource_id} from {node_name}")
            node = cluster.get_node(node_name)
            r, o = node.proxy.resource.update_resource_by_backing(
                backing_id, {"resize": arguments}
            )
            if r != 0:
                raise Exception(o["out"])
            self.resource_spec["size"] = new
        else:
            LOG.debug(f"New size {new} is the same with the original")


def get_dir_resource_class(resource_type):
    mapping = {
        "volume": _DirFileVolume,
    }

    return mapping.get(resource_type)
