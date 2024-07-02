import logging

from ..volume import _FileVolume
from .nfs_resource_handlers import get_nfs_resource_handler


LOG = logging.getLogger("avocado." + __name__)


class _NfsFileVolume(_FileVolume):
    """
    The nfs file-based volume
    """

    def _create_binding(self, node_name, need_allocate=False):
        binding = _ResourceBinding(node_name)
        binding.create_backing(self.backing_config, need_allocate)
        self._bindings[node_name] = binding

    def _destroy_binding(self, node_name):
        need_release = True if len(self._bindings) == 1 else False
        binding = self._bindings[node_name]
        binding.destroy_backing(need_release)
        del self._bindings[node_name]

    def bind(self, arguments):
        nodes = arguments["nodes"]
        for node_name in nodes:
            self._create_binding(self, node_name)

    def unbind(self, arguments):
        nodes = arguments.get("nodes")
        nodes = nodes or list(self._bindings.keys())
        for node_name in nodes:
            self._destroy_binding(self, node_name)

    def resize(self, arguments):
        pass

    def query(self, request):
        pass


def get_nfs_resource_class(resource_type):
    mapping = {
        "volume": _NfsFileVolume,
    }

    return mapping.get(resource_type)
