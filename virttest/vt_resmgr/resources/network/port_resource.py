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
        }

    def bind(self, arguments):
        """
        Bind the port resource to one worker node.
        """
        pass

    def unbind(self):
        """
        Unbind the port resource from the worker node.
        """
        pass

    def allocate(self, arguments):
        raise NotImplemented

    def release(self, arguments):
        raise NotImplemented

    def get_info(self, request):
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

        return deepcopy(config)

    def sync(self, arguments):
        raise NotImplemented

    def create(self):
        pass

    def destroy(self):
        pass
