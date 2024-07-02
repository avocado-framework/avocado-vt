import uuid
from abc import ABC, abstractmethod

from virttest.vt_cluster import cluster


class _ResourcePool(ABC):
    """
    A resource pool is used to manage resources. A resource must be
    allocated from a specific pool, and a pool can hold many resources
    """

    _POOL_TYPE = None

    def __init__(self, pool_config):
        self._config = pool_config
        self.pool_meta["uuid"] = uuid.uuid4().hex
        self._resources = dict()  # {resource id: resource object}
        self._caps = dict()

        if not set(self.attaching_nodes).difference(set(["*"])):
            self.attaching_nodes = [n.name for n in cluster.get_all_nodes()]

    @property
    def pool_name(self):
        return self.pool_meta["name"]

    @property
    def pool_id(self):
        return self.pool_meta["uuid"]

    @property
    def pool_config(self):
        return self._config

    @property
    def pool_meta(self):
        return self._config["meta"]

    @property
    def pool_spec(self):
        return self._config["spec"]

    @property
    def resources(self):
        return self._resources

    @classmethod
    def define_config(cls, pool_name, pool_params):
        access = pool_params.get("access", {})
        return {
            "meta": {
                "name": pool_name,
                "uuid": None,
                "type": pool_params["type"],
                "access": access,
            },
            "spec": {},
        }

    def update_config(self, pool_config):
        pass

    @abstractmethod
    def meet_resource_request(self, resource_type, resource_params):
        """
        Check if the pool can support a resource's allocation
        """
        raise NotImplementedError

    def define_resource_config(self, resource_type, resource_params, node_tags):
        """
        Define the resource configuration, format:
          {"meta": {...}, "spec": {...}}
        It depends on the specific resource.
        """
        res_cls = self.get_resource_class(resource_type)
        config = res_cls.define_config(resource_params, node_tags)
        config["meta"]["pool"] = self.pool_config
        return config

    @classmethod
    @abstractmethod
    def get_resource_class(cls, resource_type):
        raise NotImplementedError

    def create_resource_object(self, resource_config):
        """
        Create a resource object, no real resource allocated
        """
        meta = resource_config["meta"]
        res_cls = self.get_resource_class(meta["type"])
        res = res_cls(resource_config)
        res.create()
        self.resources[res.resource_id] = res
        return res.resource_id

    def destroy_resource_object(self, resource_id):
        """
        Destroy the resource object, all its backings should be released
        """
        res = self.resources[resource_id]
        res.destroy()
        del(self.resources[resource_id])

    def update_resource(self, resource_id, config):
        resource = self.resources.get(resource_id)
        cmd, arguments = config.popitem()

        # For the user specified nodes, we need to check if the pool
        # can be accessed from these nodes
        nodes = arguments.get("nodes")
        if nodes:
            if not set(nodes).issubset(set(self.attaching_nodes)):
                raise Exception(f"Not all worker nodes ({nodes}) can access the pool")
        handler = resource.get_update_handler(cmd)
        return handler(arguments)

    def query_resource(self, resource_id, request):
        """
        Get the reference of a specified resource
        """
        res = self.resources.get(resource_id)
        return res.query(request)

    @property
    def attaching_nodes(self):
        return self.pool_meta["access"].get("nodes")

    @attaching_nodes.setter
    def attaching_nodes(self, nodes):
        self.pool_meta["access"]["nodes"] = nodes

    """
    @property
    def pool_capability(self):
        node_name = self.attaching_nodes[0]
        node = cluster.get_node(node_name)
        return node.proxy.resource.get_pool_capability()
    """

    @classmethod
    def get_pool_type(cls):
        return cls._POOL_TYPE
