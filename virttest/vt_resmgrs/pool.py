import uuid
from abc import ABC, abstractmethod

from .resource import _Resource


class _UpdateCommand(ABC):
    _UPDATE_ACTION = None

    @abstractmethod
    @staticmethod
    def execute(resource, arguments):
        raise NotImplemented

    @property
    @classmethod
    def action(cls):
        return cls._UPDATE_ACTION


class _BindCommand(_UpdateCommand):
    _UPDATE_ACTION = 'bind'

    @staticmethod
    def execute(resource, arguments):
        pool = arguments['pool']
        nodes = arguments['nodes']
        resource.create_bindings(pool, nodes)


class _UnbindCommand(_UpdateCommand):
    _UPDATE_ACTION = 'unbind'

    @staticmethod
    def execute(resource, arguments):
        nodes = arguments.get('nodes')
        resource.destroy_bindings(nodes)


class ResizeCommand(_UpdateCommand):
    _UPDATE_ACTION = 'resize'

    @staticmethod
    def execute(resource, arguments):
        resource.update_bindings(arguments)
        resource.update_config(arguments)


class _ResourcePool(ABC):
    """
    A resource pool is used to manage resources. A resource must be
    allocated from a specific pool, and a pool can hold many resources
    """

    _POOL_TYPE = None
    _UPDATE_HANDLERS = dict()

    def __init__(self, pool_config):
        self._id = uuid.uuid4()
        self._name = None
        self._resources = dict()  # {resource id: resource object}
        self._managed_resource_types = list()
        self._accesses = dict()   # {node id: pool access object}
        self._register_update_handlers()
        self._initialize(pool_config)

    def _initialize(self, pool_config):
        self._name = pool_config.get('name')

    @classmethod
    def _register_update_handlers(cls):
        for handler_cls in _UpdateCommand.__subclasses__():
            self._UPDATE_HANDLERS[handler_cls.action] = handler_cls

    def check_resource_managed(self, spec):
        """
        Check if this is the manager which is managing the specified resource
        """
        res_type = self._get_resource_type(spec)
        return True if res_type in self._managed_resource_types else False

    def _get_resource_type(spec):
        raise NotImplementedError

    @abstractmethod
    def create_resource(self, config):
        """
        Create a resource, no real resource allocated
        """
        raise NotImplementedError

    def destroy_resource(self, resource_id):
        """
        Destroy the resource, all its backings should be released
        """
        res = self._resources[resource_id]
        res.destroy_bindings()
        del(self._resources[resource_id])

    def update_resource(self, resource_id, update_arguments):
        conf = update_arguments.copy()
        action, arguments = conf.popitem()
        res = self._resources[resource_id]
        self._UPDATE_HANDLERS[action].execute(res, arguments)

    def info_resource(self, resource_id):
        """
        Get the reference of a specified resource
        """
        res = self._resources.get(resource_id)
        return res.get_binding(node_id).backing

    @property
    def attaching_nodes(self):
        return self._accesses.keys()

    @property
    def pool_capability(self):
        node_id = self.attaching_nodes.keys()[0]
        node = get_node(node_id)
        return node.proxy.get_pool_capability()

    @property
    def pool_name(self):
        return self._name

    @property
    @classmethod
    def pool_type(cls):
        return cls._POOL_TYPE

    @property
    def pool_config(self):
        pass
