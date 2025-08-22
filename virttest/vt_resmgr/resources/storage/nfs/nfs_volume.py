import logging

from ..file_volume import _FileVolume

LOG = logging.getLogger("avocado." + __name__)


class _NfsFileVolume(_FileVolume):
    """
    The nfs file-based volume resource
    """
    def bind_backings(self, nodes):
        """
        Bind the nfs resource to the backings on the worker nodes.
        Note: A nfs volume resource can have many bindings
        """
        for node in nodes:
            _, backing_id = self._get_binding(node)
            if backing_id:
                LOG.debug(f"The nfs volume has already bound to a backing on {node.name}")
                continue

            r, o = node.proxy.resource.create_backing_object(self.get_backing_config(node.name))
            if r != 0:
                raise Exception(o["out"])

            backing_uuid = o["out"]["backing"]
            self._update_binding(node, backing_uuid)
            uri = o["out"]["spec"]["uri"]
            self._update_uri(node.name, uri)

    def unbind_backings(self, nodes):
        """
        Unbind the nfs volume from a worker node
        """
        for node in nodes:
            _, backing_id = self._get_binding(node)
            if not backing_id:
                LOG.debug(f"The nfs volume has already unbound from the backing on {node.name}")
                continue

            r, o = node.proxy.resource.destroy_backing_object(backing_id)
            if r != 0:
                raise Exception(o["out"])

            self._update_binding(node, None)
            self._update_uri(node.name, None)
