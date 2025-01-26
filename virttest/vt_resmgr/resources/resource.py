import uuid
from abc import ABC, abstractmethod
from copy import deepcopy


class _Resource(ABC):
    """
    A resource defines what users request, it's independent of a VM,
    users can request kinds of resources for any purpose. The resource
    can be bound to several backings on different worker nodes.

    Note: A resource can bind to only one backing on a worker node.
    """

    _RESOURCE_TYPE = None

    def __init__(self, resource_config):
        self._config = resource_config
        self.resource_meta["uuid"] = uuid.uuid4().hex
        self._handlers = {
            "bind": self.bind,
            "unbind": self.unbind,
            "allocate": self.allocate,
            "release": self.release,
            "sync": self.sync,
        }

    @property
    def resource_config(self):
        return self._config

    @property
    def resource_spec(self):
        return self.resource_config["spec"]

    @property
    def resource_meta(self):
        return self.resource_config["meta"]

    @property
    def resource_id(self):
        return self.resource_meta["uuid"]

    @property
    def resource_pool(self):
        return self.resource_meta["pool"]

    @resource_pool.setter
    def resource_pool(self, pool_id):
        self.resource_meta["pool"] = pool_id

    @property
    def resource_bindings(self):
        return self.resource_meta["bindings"]

    @property
    def resource_type(self):
        return self.resource_meta["type"]

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        return {
            "meta": {
                "uuid": None,
                "name": resource_name,
                "type": cls._RESOURCE_TYPE,
                "pool": None,
                "allocated": False,
                "bindings": dict(),
            },
            "spec": {},
        }

    @classmethod
    def define_config(cls, resource_name, resource_params):
        # We'll introduce new params design in future
        return cls._define_config_legacy(resource_name, resource_params)

    @abstractmethod
    def define_config_from_self(self, pool_id):
        raise NotImplementedError

    def get_update_handler(self, command):
        return self._handlers.get(command)

    @abstractmethod
    def bind(self, arguments):
        """
        Bind the resource to one or more worker nodes
        """
        raise NotImplementedError

    @abstractmethod
    def unbind(self, arguments):
        raise NotImplementedError

    @abstractmethod
    def allocate(self, arguments):
        raise NotImplementedError

    @abstractmethod
    def release(self, arguments):
        raise NotImplementedError

    @abstractmethod
    def sync(self, arguments):
        raise NotImplementedError

    def create_object(self):
        pass

    def destroy_object(self):
        pass
