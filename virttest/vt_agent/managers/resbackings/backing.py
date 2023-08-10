import uuid
from abc import ABC, abstractmethod


class _ResourceBacking(ABC):
    _RESOURCE_TYPE = None

    def __init__(self, config):
        self._uuid = uuid.uuid4()
        self._source_pool = config['spec']['pool_id']

    @property
    def uuid(self):
        return self._uuid

    @abstractmethod
    def allocate(self, pool_connection):
        pass

    @abstractmethod
    def release(self, pool_connection):
        pass

    @abstractmethod
    def update(self, pool_connection, new_spec):
        pass

    @abstractmethod
    def info(self, pool_connection):
        pass

    @property
    def resource_type(self):
        return self._RESOURCE_TYPE

    @property
    def source_pool(self):
        return self._source_pool
