import logging

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
        nodes = arguments.pop("nodes", self.resource_binding_nodes)
        if not nodes:
            raise ValueError("No worker node is set to bind to")

        for node_name in nodes:
            if not self._get_backing(node_name):
                LOG.info(f"Bind the nfs volume {self.resource_id} to node {node_name}")
                node = cluster.get_node(node_name)
                r, o = node.proxy.resource.create_backing_object(self.resource_config)
                if r != 0:
                    raise Exception(o["out"])
                self._set_backing(node_name, o["out"])
            else:
                LOG.info(
                    f"The nfs volume {self.resource_id} has already bound to {node_name}"
                )

    def unbind(self, arguments):
        """
        Unbind the nfs volume from a worker node
        """
        nodes = arguments.pop("nodes", self.resource_binding_nodes)
        for node_name in nodes:
            backing_id = self._get_backing(node_name)
            if backing_id:
                LOG.info(
                    f"Unbind the nfs volume {self.resource_id} from node {node_name}"
                )
                node = cluster.get_node(node_name)
                r, o = node.proxy.resource.destroy_backing_object(backing_id)
                if r != 0:
                    raise Exception(o["out"])
                self._set_backing(node_name, None)
            else:
                LOG.info(
                    f"The nfs volume {self.resource_id} was not bound to {node_name}"
                )


def get_nfs_resource_class(resource_type):
    mapping = {
        "volume": _NfsFileVolume,
    }

    return mapping.get(resource_type)
