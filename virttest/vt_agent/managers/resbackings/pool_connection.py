import uuid
from abc import ABC, abstractmethod


class _ResourcePoolAccess(ABC):

    @abstractmethod
    def __init__(self, pool_access_config):
        pass


class _ResourcePoolConnection(ABC):

    def __init__(self, pool_config, pool_access_config):
        self._connected_pool = pool_config['pool_id']

    @abstractmethod
    def startup(self):
        pass

    @abstractmethod
    def shutdown(self, backing):
        pass

    @abstractmethod
    def connected(self):
        return False
