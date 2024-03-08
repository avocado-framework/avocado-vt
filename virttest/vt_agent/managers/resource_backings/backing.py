import uuid
from abc import ABC, abstractmethod


class _ResourceBacking(ABC):
    _BINDING_RESOURCE_TYPE = None
    _SOURCE_POOL_TYPE = None

    def __init__(self, backing_config):
        self._uuid = uuid.uuid4().hex
        self._source_pool_id = backing_config["meta"]["pool"]
        self._resource_id = backing_config["meta"]["uuid"]
        self._handlers = {
            "allocate": self.allocate_resource,
            "release": self.release_resource,
            "sync": self.get_resource_info,
        }

    def create(self, pool_conn):
        pass

    def destroy(self, pool_conn):
        self._uuid = None
        self._resource_id = None

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
        return self._handlers[cmd]

    @abstractmethod
    def allocate_resource(self, pool_connection, arguments=None):
        raise NotImplementedError

    @abstractmethod
    def release_resource(self, pool_connection, arguments=None):
        raise NotImplementedError

    @abstractmethod
    def get_resource_info(self, pool_connection, arguments=None):
        raise NotImplementedError
