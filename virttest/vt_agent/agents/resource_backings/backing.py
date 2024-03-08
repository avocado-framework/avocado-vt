import uuid
from abc import ABC, abstractmethod


class _ResourceBacking(ABC):
    _BINDING_RESOURCE_TYPE = None
    _SOURCE_POOL_TYPE = None

    def __init__(self, backing_config):
        self._uuid = uuid.uuid4().hex
        self._source_pool_id = backing_config["meta"]["pool"]["meta"]["uuid"]
        self._resource_id = backing_config["meta"]["uuid"]
        self._handlers = {
            "allocate": self.allocate_resource,
            "release": self.release_resource,
            "sync": self.sync_resource,
        }

    def create(self, pool_conn):
        pass

    def destroy(self, pool_conn):
        pass

    @classmethod
    def get_pool_type(cls):
        return cls._SOURCE_POOL_TYPE

    @classmethod
    def get_resource_type(cls):
        return cls._BINDING_RESOURCE_TYPE

    @property
    def binding_resource_id(self):
        return self._resource_id

    @property
    def source_pool_id(self):
        return self._source_pool_id

    @property
    def backing_id(self):
        return self._uuid

    def get_update_handler(self, cmd):
        return self._handlers.get(cmd)

    @abstractmethod
    def allocate_resource(self, pool_connection, arguments):
        pass

    @abstractmethod
    def release_resource(self, pool_connection, arguments):
        pass

    @abstractmethod
    def info_resource(self, pool_connection):
        pass

    @abstractmethod
    def sync_resource(self, pool_connection, arguments):
        pass

