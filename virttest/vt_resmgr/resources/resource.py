import uuid
from abc import ABC, abstractmethod
from copy import deepcopy

from virttest.vt_cluster import cluster


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
    def resource_binding_nodes(self):
        return [d["node"] for d in self.resource_bindings]

    @property
    def resource_type(self):
        return self.resource_meta["type"]

    def _set_backing(self, node_name, backing_id):
        for binding in self.resource_bindings:
            if binding["node"] == node_name:
                binding["backing"] = backing_id
                break

    def _get_backing(self, node_name):
        for binding in self.resource_bindings:
            if binding["node"] == node_name:
                return binding["backing"]
        return None

    def _get_binding_nodes(self, pool_selectors):
        """
        Get the worker nodes where the resource can be accessed.
        The nodes can be set in the xxx_pool_selectors params, e.g.
          volume_pool_selectors_image1 = [
            {"key": "access.nodes", "operator": "contains", values": "node1 node2"},
          ]
        When it's not set, use all nodes in the partition.

        :param pool_selectors: The cartesian param: xxx_pool_selectors, e.g.
                               volume_pool_selectors
        :type resource_name: list
        """
        nodes = list()
        for d in pool_selectors:
            if "access.nodes" in d:
                nodes = [cluster.get_node_by_tag(t).name for t in d["values"].split()]
                break
        return [n.name for n in cluster.partition.nodes] if not nodes else nodes

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        return {
            "meta": {
                "uuid": None,
                "name": resource_name,
                "type": cls._RESOURCE_TYPE,
                "pool": None,
                "allocated": False,
                "bindings": list(),
            },
            "spec": {},
        }

    @classmethod
    def define_config(cls, resource_name, resource_params):
        # We'll introduce new params design in future
        return cls._define_config_legacy(resource_name, resource_params)

    def get_update_handler(self, command):
        return self._handlers.get(command)

    @abstractmethod
    def clone(self):
        """
        Clone the resource, return a new resource object
        """
        raise NotImplementedError

    @abstractmethod
    def bind(self, arguments):
        """
        Bind the resource to one or more worker nodes
        """
        raise NotImplementedError

    @abstractmethod
    def unbind(self, arguments):
        """
        Unbind the resource to one or more worker nodes
        """
        raise NotImplementedError

    @abstractmethod
    def allocate(self, arguments):
        """
        Allocate the resource
        """
        raise NotImplementedError

    @abstractmethod
    def release(self, arguments):
        """
        Release the resource
        """
        raise NotImplementedError

    @abstractmethod
    def sync(self, arguments):
        """
        Sync the resource configuration
        """
        raise NotImplementedError

    def create_object(self):
        pass

    def destroy_object(self):
        pass
