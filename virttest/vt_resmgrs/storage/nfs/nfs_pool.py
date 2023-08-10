import logging

from ...pool import _ResourcePool
from .nfs_resource import get_resource_class


LOG = logging.getLogger('avocado.' + __name__)


class _NfsPool(_ResourcePool):
    _POOL_TYPE = 'nfs'

    def _initialize(self, pool_config):
        super().__init__(pool_config)
        self._nfs_server = pool_config['nfs_server_ip']
        self._export_dir = pool_config['nfs_mount_src']

    def create_resource(self, resource_config):
        spec = resource_config['spec']
        cls = get_resource_class(spec['type'])
        res = cls(resource_config)
        self._resources[res.resource_id] = res
        return res.resource_id
