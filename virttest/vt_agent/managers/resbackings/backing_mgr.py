from abc import ABC, abstractmethod


class _ResourceBackingManager(ABC):
    _ATTACHED_POOL_TYPE = None

    def __init__(self):
        self._pool_connections = dict()
        self._backings = dict()

    @abstractmethod
    def create_pool_connection(self, pool_config, pool_access_config):
        pass

    def destroy_pool_connection(self, pool_id):
        pool_conn = self._pool_connections[pool_id]
        pool_conn.shutdown()
        del(self._pool_connections[pool_id])

    @abstractmethod
    def create_backing(self, config, need_allocate=False):
        pass

    def destroy_backing(self, backing_id, need_release=False):
        backing = self._backings[backing_id]
        pool_conn = self._pool_connections[backing.source_pool]
        if need_release:
            backing.release_resource(pool_conn)
        del(self._backings[backing_id])

    def update_backing(self, backing_id, config):
        backing = self._backings[backing_id]
        pool_conn = self._pool_connections[backing.source_pool]
        backing.update(pool_conn, config)

    def get_backing(self, backing_id):
        return self._backings.get(backing_id)

    def info_backing(self, backing_id):
        return self._backings[backing_id].to_specs()
