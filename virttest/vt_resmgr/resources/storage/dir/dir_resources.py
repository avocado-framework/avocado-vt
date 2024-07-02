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
        nodes = list(self.resource_bindings.keys())
        if self.resource_bindings[nodes[0]] is not None:
            LOG.warning("The dir volume %s has already bound to node %s.",
                        self.resource_id, nodes[0])
        else:
            LOG.debug("Bind the dir volume %s to node %s.",
                      self.resource_id, nodes[0])
            node = cluster.get_node_by_tag(nodes[0])
            backing_id = node.proxy.resource.create_backing(self.backing_config)
            self.resource_bindings[nodes[0]] = backing_id

    def unbind(self, arguments):
        """
        Unbind the resource from a worker node.
        Note: A dir resource must be released before unbinding
              because it has only one binding
        """
        node_name, backing_id = list(self.resource_bindings.items())[0]
        LOG.debug("Unbind the dir volume %s from node %s.",
                  self.resource_id, node_name)
        node = cluster.get_node_by_tag(node_name)
        node.proxy.resource.destroy_backing(backing_id)
        self.resource_bindings[node_name] = None

    def sync(self, arguments):
        LOG.debug(f"Sync up the conf for the dir volume {self.resource_id}")
        node_name, backing_id = list(self.resource_bindings.items())[0]
        node = cluster.get_node_by_tag(node_name)
        r, o = node.proxy.resource.update_backing(backing_id,
                                                  {"sync": arguments})
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.resource_meta["allocated"] = config["meta"]["allocated"]
        self.resource_spec["uri"] = config["spec"]["uri"]
        self.resource_spec["allocation"] = config["spec"]["allocation"]

    def allocate(self, arguments):
        uri = self.resource_spec["uri"]
        if uri:
            LOG.debug(f"Use a specified volume({uri}) instead of allocating a new one")
            return

        node_name, backing_id = list(self.resource_bindings.items())[0]
        LOG.debug(f"Allocate the dir volume {self.resource_id} from node {node_name}.")
        node = cluster.get_node_by_tag(node_name)
        r, o = node.proxy.resource.update_backing(backing_id,
                                                  {"allocate": arguments})
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.resource_meta["allocated"] = config["meta"]["allocated"]
        self.resource_spec["uri"] = config["spec"]["uri"]
        self.resource_spec["allocation"] = config["spec"]["allocation"]

    def release(self, arguments):
        node_name, backing_id = list(self.resource_bindings.items())[0]
        node = cluster.get_node_by_tag(node_name)
        LOG.debug(f"Release the dir volume {self.resource_id} from node {node_name}.")
        r, o = node.proxy.resource.update_backing(backing_id,
                                                  {"release": arguments})
        if r != 0:
            raise Exception(o["error"])

    def resize(self, arguments):
        """
        Resize the local dir volume resource
        """
        new = int(normalize_data_size(arguments["size"], "B"))
        if new != self.resource_spec["size"]:
            node_name, backing_id = list(self.resource_bindings.items())[0]
            LOG.debug(f"Resize the dir volume {self.resource_id} from node {node_name}")
            node = cluster.get_node_by_tag(node_name)
            r, o = node.proxy.resource.update_backing(backing_id, {"resize": arguments})
            if r != 0:
                raise Exception(o["error"])
            self.resource_spec["size"] = new
        else:
            LOG.debug(f"Updated size({new}) is the same with the original")

    def query(self, request):
        LOG.debug(f"Query {request} for dir volume {self.resource_id}")
        self.sync(arguments=dict())


def get_dir_resource_class(resource_type):
    mapping = {
        "volume": _DirFileVolume,
    }

    return mapping.get(resource_type)
