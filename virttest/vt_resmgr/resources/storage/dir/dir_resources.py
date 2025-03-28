import logging

from virttest.vt_cluster import cluster

from ..volume import _FileVolume

LOG = logging.getLogger("avocado." + __name__)


class _DirFileVolume(_FileVolume):
    """
    The directory file-based volume
    """

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        config = super()._define_config_legacy(resource_name, resource_params)
        if len(config["meta"]["bindings"]) > 1:
            raise ValueError("Only one node can be bound to a dir volume")
        return config

    def bind(self, arguments):
        """
        Bind the resource to a backing on a worker node.
        Note: A local dir resource has one and only one binding in the cluster
        """
        nodes = arguments.pop("nodes", self.resource_binding_nodes)
        if len(nodes) > 1:
            raise ValueError("Try to bind a dir resource to more than one node")

        if not self._get_backing(nodes[0]):
            LOG.info(f"Bind the dir volume {self.resource_id} to {nodes[0]}")
            node = cluster.get_node(nodes[0])
            r, o = node.proxy.resource.create_backing_object(self.resource_config)
            if r != 0:
                raise Exception(o["out"])
            self._set_backing(nodes[0], o["out"])
        else:
            LOG.warning(
                f"The dir volume {self.resource_id} has already bound to {node_name}"
            )

    def unbind(self, arguments):
        """
        Unbind the resource from a worker node.
        Note: A dir resource must be released before unbinding
              because it has only one binding
        """
        nodes = arguments.pop("nodes", self.resource_binding_nodes)
        if len(nodes) > 1:
            raise ValueError("Try to unbind a dir resource from more than one node")

        node_name = self.resource_bindings[0]["node"]
        backing_id = self._get_backing(node_name)
        LOG.info(f"Unbind the dir volume {self.resource_id} from {node_name}")
        node = cluster.get_node(node_name)
        r, o = node.proxy.resource.destroy_backing_object(backing_id)
        if r != 0:
            raise Exception(o["out"])
        self._set_backing(node_name, None)


def get_dir_resource_class(resource_type):
    mapping = {
        "volume": _DirFileVolume,
    }

    return mapping.get(resource_type)
