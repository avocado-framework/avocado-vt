import logging

from ..volume import _FileVolume


LOG = logging.getLogger('avocado.' + __name__)


class _NfsFileVolume(_FileVolume):
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
        #self._path = spec.get('filename')
        self._capacity = spec['size']
        self._allocation = 0

"""
    def allocate(self, nodes=None):
        if nodes:
            node_id = nodes[0]
            binding = self._bindings[node_id]
        else:
            node_id, binding = list(self._bindings.items())[0]
        node = get_node(node_id)
        node.proxy.allocate(binding.backing_id)

    def release(self, nodes=None):
        if nodes:
            node_id = nodes[0]
            binding = self._bindings[node_id]
        else:
            node_id, binding = list(self._bindings.items())[0]
        node = get_node(node_id)
        node.proxy.release(binding.backing_id)
"""

    def _create_binding(self, pool_id, node_id, need_allocate=False):
        binding = _ResourceBinding(pool_id, node_id)
        binding.create_backing(self.resource_info, need_allocate)
        self._bindings[node_id] = binding

    def create_bindings(self, pool_id, nodes):
        """
        Create the bindings for a nfs resource
        A NFS resource will only be allocated once when creating the
        first binding, for the other bindings, there's no allocation
        """
        allocated = True if self._bindings else False
        bindings = list()
        node_list = nodes.copy()
        try:
            # Create the first binding with allocation
            if not allocated:
                node_id = node_list.pop(0)
                self._create_binding(pool_id, node_id, True)
                bindings.append(node_id)

            # Create the bindings without allocation
            for node_id in node_list:
                self._create_binding(pool_id, node_id, False)
                bindings.append(node_id)
        except Exception:
            # Remove the created bindings when an error occurs
            for node_id in bindings:
                self._destroy_binding(node_id)

    def _destroy_binding(self, node_id):
        need_release = True if len(self._bindings) == 1 else False
        binding = self._bindings[node_id]
        binding.destroy_backing(need_release)
        del(self._bindings[node_id])

    def destroy_bindings(self, nodes=None):
        nodes = list(self._bindings.keys()) if not nodes else nodes
        for node_id in nodes:
            self._destroy_binding(self, node_id):

    def _update_binding(self, binding, config):
        pass

    def update_bindings(self, config):
        for node_id, binding in self._bindings.items():
            self._update_binding(node_id, config)

    @property
    def resource_info(self):
        pass


def get_resource_class(resource_type):
    return _NfsFileVolume
