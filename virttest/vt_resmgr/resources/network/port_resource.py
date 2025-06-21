import uuid
from abc import abstractmethod

from ..resource import _Resource


class _PortResource(_Resource):
    """
    This class, inherited from _Resource, defines the port resource model.
    """

    _RESOURCE_TYPE = "port"

    def __init__(self, resource_config):
        super().__init__(resource_config)
        self._handlers = {
            "bind": self.bind,
            "unbind": self.unbind,
            "allocate": self.allocate,
            "release": self.release,
            "sync": self.sync,
        }

    def bind(self, arguments):
        """
        Bind the port resource to one worker node.
        """
        raise NotImplemented

    def unbind(self, arguments):
        """
        Unbind the port resource from the worker node.
        """
        raise NotImplemented

    def allocate(self, arguments):
        raise NotImplemented

    def release(self, arguments):
        raise NotImplemented

    def sync(self, arguments):
        raise NotImplemented

    def create_object(self):
        pass

    def destroy_object(self):
        pass

    def define_config_from_self(self, pool_id):
        pass

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        return {
            "meta": {
                "name": resource_name,
                "uuid": None,
                "type": cls._RESOURCE_TYPE,
                "pool": None,
                "allocated": False,
                "bindings": dict(),
            },
            "spec": {},
        }
