import uuid
from abc import ABC, abstractmethod


class _ResourceBinding(object):
    """
    A binding binds a resource to an allocated resource backing
    at a worker node. A resource can have many bindings, but one
    binding can only bind one backing at one worker node.
    """

    def __init__(self, pool_id, node_id):
        self._pool_id = pool_id
        self._node_id = node_id
        self._backing_id = None

    def create_backing(self, resource_config, need_allocate=False):
        """
        Create a resource backing object via RPC
        """
        node = get_node(self._node_id)
        self._backing_id = node.proxy.create_backing(resource_config,
                                                     need_allocate)

    def destroy_backing(self, need_release=False):
        """
        Destroy the resource backing object via RPC
        """
        node = get_node(self._node_id)
        node.proxy.destroy_backing(self._backing_id, need_release)

    def update_backing(self, spec):
        node = get_node(self._node_id)
        node.proxy.update(self._backing_id, spec)

    def bind_backing(self):
        """
        Bind a resource backing object via RPC
        """
        node = get_node(self._node_id)
        self._backing_id = node.proxy.bind(config)

    def unbind_backing(self):
        """
        Create a resource backing object via RPC
        """
        node = get_node(self._node_id)
        self._backing_id = node.proxy.unbind(config)

    @property
    def reference(self):
        return {'node': self.node_id, 'id': self.backing_id}

    @property
    def node_id(self):
        """
        Get the node id of the resource backing
        """
        return self._node_id

    @property
    def backing_id(self):
        """
        Get the resource backing id
        """
        return self._backing_id


class _Resource(ABC):
    """
    A resource defines what users request, it's independent of a VM,
    users can request a kind of resources for any purpose, it can bind
    several allocated resource backings at different worker nodes.

    The common attributes of a resource:
      meta:
        resource id
        access:
          nodes:
          permission:
        references:
          node id
          backing id
      spec:
        resource pood id
        specific attributes
    """

    _RESOURCE_TYPE = None

    def __init__(self, resource_config):
        self._id = uuid.uuid4()
        self._name = None
        self._bindings = dict()
        self._initialize(resource_config)

    def _initialize(self, resource_config):
        self._pool_id = resource_config.get('pool_id')

    @property
    def resource_type(cls):
        raise cls._RESOURCE_TYPE

    @property
    def resource_id(self):
        return self._id

    @property
    def resource_pool(self):
        return self._pool_id

    @property
    @abstractmethod
    def resource_info(self):
        raise NotImplemented

    @abstractmethod
    def create_bindings(self, nodes):
        """
        Create the bindings on the specified worker nodes
        """
        raise NotImplemented

    @abstractmethod
    def destroy_bindings(self, nodes):
        """
        Destroy the bindings on the specified worker nodes
        """
        raise NotImplemented

    @abstractmethod
    def update_bindings(self, config):
        raise NotImplementedError

    @abstractmethod
    def _update_meta(self, new_meta):
        raise NotImplementedError

    @abstractmethod
    def _update_spec(self, new_spec):
        raise NotImplementedError

    def update_config(self, new_config):
        meta = new_config.get('meta')
        if meta is not None:
            self._update_meta(meta)

        spec = new_config.get('spec')
        if spec is not None:
            self._update_spec(spec)
