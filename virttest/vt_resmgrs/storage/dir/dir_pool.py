import logging

from ...pool import _ResourcePool
from .dir_resource import _get_resource_class


LOG = logging.getLogger('avocado.' + __name__)


class _DirPool(_ResourcePool):
    _POOL_TYPE = 'nfs'

    def _initialize(self, pool_config):
        super().__init__(pool_config)
        self._root_dir = pool_config['root_dir']

    def create_resource(self, resource_config):
        spec = resource_config['spec']
        cls = _get_resource_class(spec['type'])
        res = cls(resource_config)
        self._resources[res.resource_id] = res
        return res.resource_id
