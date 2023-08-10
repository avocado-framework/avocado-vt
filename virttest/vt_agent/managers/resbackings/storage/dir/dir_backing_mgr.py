from ...backing_mgr import _ResourceBackingManager
from .dir_backing import _get_backing_class
from .dir_pool_connection import _DirPoolConnection


class _DirBackingManager(_ResourceBackingManager):
    _ATTACHED_POOL_TYPE = 'nfs'

    def __init__(self):
        super().__init__()

    def create_pool_connection(self, pool_config, pool_access_config):
        pool_conn = _DirPoolConnection(pool_config, pool_access_config)
        pool_conn.startup()
        self._pool_connections[pool_id] = pool_conn

    def destroy_pool_connection(self, pool_id):
        pool_conn = self._pool_connections[pool_id]
        pool_conn.shutdown()
        del(self._pool_connections[pool_id])

    def create_backing(self, config, need_allocate=False):
        pool_id = config['pool_id']
        pool_conn = self._pool_connections[pool_id]
        backing_class = _get_backing_class(config['resource_type'])
        backing = backing_class(config)
        self._backings[backing.uuid] = backing
        if need_allocate:
            backing.allocate(pool_conn)

    def destroy_backing(self, backing_id, need_release=False):
        backing = self._backings[backing_id]
        pool_conn = self._pool_connections[backing.source_pool]
        if need_release:
            backing.release(pool_conn)
        del(self._backings[backing_id])

    def update_backing(self, backing_id, new_backing_spec):
        backing = self._allocated_backings[backing_id]
        pool_conn = self._pool_connections[backing.source_pool]
        backing.update(pool_conn, new_backing_spec)

    def info_backing(self, backing_id):
        backing = self._allocated_backings[backing_id]
        pool_conn = self._pool_connections[backing.source_pool]
        return backing.info(pool_conn)
