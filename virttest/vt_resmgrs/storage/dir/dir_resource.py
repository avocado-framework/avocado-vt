import logging

from ..volume import _FileVolume


LOG = logging.getLogger('avocado.' + __name__)


class _DirFileVolume(_FileVolume):
    """
    The nfs file-based volume

    Resource attributes:
    meta:
      resource id
      references:
        node id
        reference id
    spec:
      size
      name
      path
    """

    def _initialize(self, resource_config):
        super()._initialize(resource_config)
        meta = resource_config['meta']
        spec = resource_config['spec']
        self._name = spec['name']
        self._capacity = spec['size']
        self._allocation = 0

    def create_bindings(self, pool_id, nodes):
        """
        A local dir resource has only one binding,
        it is allocated when creating the binding
        """
        if len(nodes) != 1:
            LOG.warning('A dir resource should have one binding only')

        binding = _ResourceBinding(pool_id, nodes[0])
        binding.create_backing(self.resource_info, True)
        self._bindings[node_id] = binding

    def destroy_bindings(self, nodes=None):
        """
        Always release the resource when destroying its binding
        """
        node_id = list(self._bindings.keys())[0]
        self._bindings[node_id].destroy_backing(True)
        del(self._bindings[node_id])

    def _update_binding(self, binding, config):
        pass

    def update_bindings(self, config):
        for node_id, binding in self._bindings.items():
            self._update_binding(node_id, config)

    @property
    def resource_info(self):
        pass


def _get_resource_class(resource_type):
    return _DirFileVolume
