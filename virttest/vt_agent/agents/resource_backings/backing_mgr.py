from abc import ABC, abstractmethod
from .resbackings import get_backing_class
from .resbackings import get_pool_connection_class


class _ResourceBackingManager(ABC):
    _ATTACHED_POOL_TYPE = None

    def __init__(self):
        self._pool_connections = dict()
        self._backings = dict()

    @abstractmethod
    def create_pool_connection(self, pool_params):
        pool_id = pool_params["uuid"]
        pool_type = pool_params["type"]
        pool_conn_class = get_pool_connection_class(pool_type)
        pool_conn = pool_conn_class(pool_params)
        pool_conn.startup()
        self._pool_connections[pool_id] = pool_conn

    def destroy_pool_connection(self, pool_id):
        pool_conn = self._pool_connections[pool_id]
        pool_conn.shutdown()
        del self._pool_connections[pool_id]

    @abstractmethod
    def create_backing(self, config, need_allocate=False):
        pass

    def destroy_backing(self, backing_id, need_release=False):
        backing = self._backings[backing_id]
        pool_conn = self._pool_connections[backing.source_pool_id]
        if need_release:
            backing.release_resource(pool_conn)
        del self._backings[backing_id]

    def update_backing(self, backing_id, config):
        backing = self._backings[backing_id]
        pool_conn = self._pool_connections[backing.source_pool_id]
        backing.update(pool_conn, config)

    def get_backing(self, backing_id):
        return self._backings.get(backing_id)

    def info_backing(self, backing_id):
        return self._backings[backing_id].to_specs()
