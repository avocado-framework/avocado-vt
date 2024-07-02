import logging

from .resource_backings import (
    get_resource_backing_class,
    get_pool_connection_class,
)


LOG = logging.getLogger("avocado.service." + __name__)


class _ResourceBackingAgent(object):

    def __init__(self):
        self._pool_connections = dict()
        self._backings = dict()

    def create_pool_connection(self, pool_id, pool_config):
        LOG.info(f"Connect to pool '{pool_id}'")
        pool_type = pool_config["meta"]["type"]
        pool_conn_class = get_pool_connection_class(pool_type)
        pool_conn = pool_conn_class(pool_config)
        pool_conn.startup()
        self._pool_connections[pool_id] = pool_conn

    def destroy_pool_connection(self, pool_id):
        LOG.info(f"Disconnect to pool '{pool_id}'")
        pool_conn = self._pool_connections[pool_id]
        pool_conn.shutdown()
        del(self._pool_connections[pool_id])

    def create_backing(self, backing_config):
        LOG.info("Create a backing object for resource %s",
                 backing_config["meta"]["uuid"])
        pool_id = backing_config["meta"]["pool"]["meta"]["uuid"]
        pool_conn = self._pool_connections[pool_id]
        pool_type = pool_conn.get_pool_type()
        res_type = backing_config["meta"]["type"]
        backing_class = get_resource_backing_class(pool_type, res_type)
        backing = backing_class(backing_config)
        backing.create(pool_conn)
        self._backings[backing.backing_id] = backing
        return backing.backing_id

    def destroy_backing(self, backing_id):
        backing = self._backings[backing_id]
        LOG.info(f"Destroy the backing object for resource {backing.binding_resource_id}")
        pool_conn = self._pool_connections[backing.source_pool_id]
        backing.destroy(pool_conn)
        del(self._backings[backing_id])

    def update_backing(self, backing_id, new_config):
        backing = self._backings[backing_id]
        LOG.info(f"Update the resource {backing.binding_resource_id}")
        pool_conn = self._pool_connections[backing.source_pool_id]
        cmd, arguments = new_config.popitem()
        handler = backing.get_update_handler(cmd)
        return handler(pool_conn, arguments)

    def info_backing(self, backing_id):
        backing = self._backings[backing_id]
        pool_conn = self._pool_connections[backing.source_pool_id]
        return backing.info_resource(pool_conn)


resbacking_agent = _ResourceBackingAgent()
