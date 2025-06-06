import logging
import os
import pickle

from vt_agent.core.data_dir import BACKING_MGR_ENV_FILENAME

from .resource_backings import get_pool_connection_class, get_resource_backing_class

LOG = logging.getLogger("avocado.service." + __name__)


class ResourceBackingManager(object):
    def __init__(self):
        self._backings = dict()
        self._pool_connections = dict()
        if os.path.isfile(BACKING_MGR_ENV_FILENAME):
            self._load()

    def _load(self):
        with open(BACKING_MGR_ENV_FILENAME, "rb") as f:
            self._dump_data = pickle.load(f)

    def _dump(self):
        with open(BACKING_MGR_ENV_FILENAME, "wb") as f:
            pickle.dump(self._dump_data, f)

    @property
    def _dump_data(self):
        return {
            "pool_connections": self._pool_connections,
        }

    @_dump_data.setter
    def _dump_data(self, data):
        self._pool_connections = data.get("pool_connections", dict())

    def startup(self):
        # FIXME
        self.teardown()

    def teardown(self):
        if os.path.exists(BACKING_MGR_ENV_FILENAME):
            os.unlink(BACKING_MGR_ENV_FILENAME)
        self._dump_data = dict()

    def create_pool_connection(self, pool_id, pool_config):
        r, o = 0, dict()
        try:
            pool_type = pool_config["meta"]["type"]
            pool_conn_class = get_pool_connection_class(pool_type)
            pool_conn = pool_conn_class(pool_config)
            pool_conn.open()
            self._pool_connections[pool_id] = pool_conn
        except Exception as e:
            r, o["out"] = 1, str(e)
            LOG.debug(f"Failed to connect to pool({pool_id}): {str(e)}")

        if r == 0:
            self._dump()

        return r, o

    def destroy_pool_connection(self, pool_id):
        r, o = 0, dict()
        try:
            pool_conn = self._pool_connections.pop(pool_id)
            pool_conn.close()
        except Exception as e:
            r, o["out"] = 1, str(e)
            LOG.debug(f"Failed to disconnect pool({pool_id}): {str(e)}")

        if r == 0:
            self._dump()

        return r, o

    def create_backing_object(self, backing_config):
        r, o = 0, dict()
        try:
            pool_id = backing_config["meta"]["pool"]
            pool_conn = self._pool_connections[pool_id]
            pool_type = pool_conn.get_pool_type()
            res_type = backing_config["meta"]["type"]
            backing_class = get_resource_backing_class(pool_type, res_type)
            backing = backing_class(backing_config)
            backing.create(pool_conn)
            self._backings[backing.backing_id] = backing
            o["out"] = backing.backing_id
        except Exception as e:
            r, o["out"] = 1, str(e)
            LOG.debug(
                "Failed to create backing object for resource %s: %s",
                backing_config["meta"]["uuid"],
                str(e),
            )
        return r, o

    def destroy_backing_object(self, backing_id):
        r, o = 0, dict()
        try:
            backing = self._backings.pop(backing_id)
            pool_conn = self._pool_connections[backing.source_pool_id]
            backing.destroy(pool_conn)
        except Exception as e:
            r, o["out"] = 1, str(e)
            LOG.debug(f"Failed to destroy backing object({backing_id}): {str(e)}")
        return r, o

    def update_resource_by_backing(self, backing_id, new_config):
        r, o = 0, dict()
        try:
            backing = self._backings[backing_id]
            pool_conn = self._pool_connections[backing.source_pool_id]
            cmd, arguments = new_config.popitem()
            handler = backing.get_update_handler(cmd)
            ret = handler(pool_conn, arguments)
            if ret:
                o["out"] = ret
        except Exception as e:
            r, o["out"] = 1, str(e)
            LOG.debug(f"Failed to update resource by backing ({backing_id}): {str(e)}")
        return r, o

    def get_resource_info_by_backing(self, backing_id):
        r, o = 0, dict()
        try:
            backing = self._backings[backing_id]
            pool_conn = self._pool_connections[backing.source_pool_id]
            o["out"] = backing.get_resource_info(pool_conn)
        except Exception as e:
            r, o["out"] = 1, str(e)
            LOG.debug(f"Failed to info resource by backing ({backing_id}): {str(e)}")
        return r, o
