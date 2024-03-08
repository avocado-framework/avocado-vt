from abc import ABC, abstractmethod


class _ResourcePoolAccess(ABC):
    @abstractmethod
    def __init__(self, pool_access_config):
        pass


class _ResourcePoolConnection(ABC):
    _CONNECT_POOL_TYPE = None

    def __init__(self, pool_config):
        self._pool_id = pool_config["meta"]["uuid"]

    @classmethod
    def get_pool_type(cls):
        return cls._CONNECT_POOL_TYPE

    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def close(self):
        pass

    @property
    @abstractmethod
    def connected(self):
        return False
