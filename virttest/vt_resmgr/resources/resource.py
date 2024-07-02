import uuid
from abc import ABC, abstractmethod


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
        }

    @classmethod
    def resource_type(cls):
        raise cls._RESOURCE_TYPE

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
        return self.resource_meta["pool"]["meta"]["uuid"]

    @property
    def resource_bindings(self):
        return self.resource_meta["bindings"]

    @classmethod
    def _define_config_legacy(cls, resource_params, node_tags):
        return {
            "meta": {
                "uuid": None,
                "type": None,
                "pool": None,
                "allocated": False,
                "bindings": {n: None for n in node_tags},
            },
            "spec": {},
        }

    @classmethod
    def define_config(cls, resource_params, node_tags):
        return cls._define_config_legacy(resource_params, node_tags)

    @property
    def backing_config(self):
        """
        Define the required information of the resource, used
        for allocating the resource on the worker nodes
        """
        return self.resource_config
        #config = dict()
        #config["uuid"] = self.resource_id
        #config["pool"] = self.resource_pool
        #config["type"] = self.resource_type
        #return config

    def get_update_handler(self, command):
        return self._handlers.get(command)

    @abstractmethod
    def bind(self, arguments):
        """
        Bind the resource to one or more worker nodes
        """
        raise NotImplemented

    @abstractmethod
    def unbind(self, arguments):
        raise NotImplemented

    @abstractmethod
    def allocate(self, arguments):
        raise NotImplemented

    @abstractmethod
    def release(self, arguments):
        raise NotImplemented

    def query(self, request):
        r, o = self.sync(dict())
        if r != 0:
            raise Exception(o["out"])

        config = self.resource_config
        if request is not None:
            for item in request.split("."):
                if item in config:
                    config = config[item]
                else:
                    raise ValueError(request)
            else:
                config = {item: config}

        return config

    @abstractmethod
    def sync(self, arguments):
        raise NotImplemented

    def create(self):
        pass

    def destroy(self):
        pass
