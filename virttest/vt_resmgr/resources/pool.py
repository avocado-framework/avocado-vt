import uuid
from abc import ABC, abstractmethod
from copy import deepcopy

from virttest.vt_cluster import cluster, selector


class _PoolSelector(object):
    """
    Example:
    nodes = node1 node2
    images = image1
    image_chain_image1 = base image1
    volume_pool_selectors_base = [{"key": "type", "operator": "==", "values": "nfs"},
    volume_pool_selectors_base += {"key": "access.nodes", "operator": "contains", "values": "node1 node2"},]
    volume_pool_selectors_image1 = [{"key": "access.nodes", "operator": "contains", values": "node1"},]
    """

    def __init__(self, pool_selectors):
        self._pool_selectors = ast.literal_eval(pool_selectors)
        self._match_expressions = []

        for pool_selector in self._pool_selectors:
            key, operator, values = self._convert(pool_selector)
            self._match_expressions.append(selector._MatchExpression(key, operator, values))

    def _convert(self, pool_selector):
        keys = pool_selector.get("key").split(".")
        operator = pool_selector.get("operator")
        values = pool_selector.get("values")
        if "access.nodes" == key:
            values = [cluster.get_node_by_tag(tag).name for tag in values.split()]
        return keys, operator, values

    def _get_values(self, keys, config):
        config = config["meta"] if keys[0] in config["meta"] else config["spec"]
        for key in keys:
            if key in config:
                config = config[key]
            else:
                raise ValueError
        return config

    def match(self, pool):
        for match_expression in self._match_expressions:
            key = match_expression.key
            op = match_expression.operator
            values = match_expression.values
            config_values = self._get_values(key, pool.pool_config)
            if not selector._Operator.operate(op, config_values, values):
                return False
        return True


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

    def customize_pool_config(self, node_name):
        """
        Customized pool configuration, which is passed to the resource backing
        manager, describes the resource pool, the backing manager uses it to
        connect to the physical pool from the worker node.
        """
        return self.pool_config

    @property
    def pool_meta(self):
        return self._config["meta"]

    @property
    def pool_spec(self):
        return self._config["spec"]

    @property
    def resources(self):
        return self._resources

    def get_info(self, verbose=False):
        return deepcopy(self.pool_config)

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

    @abstractmethod
    def meet_conditions(self, conditions):
        """
        Check if the pool can meet the conditions
        """
        raise NotImplementedError

    def define_resource_config(self, resource_name, resource_type, resource_params):
        """
        Define the resource configuration, format:
          {"meta": {...}, "spec": {...}}
        It depends on the specific resource.
        """
        res_cls = self.get_resource_class(resource_type)
        config = res_cls.define_config(resource_name, resource_params)

        config["meta"].update(
            {
                "pool": self.pool_id,
            }
        )

        return config

    @classmethod
    @abstractmethod
    def get_resource_class(cls, resource_type):
        """
        Get the resource class by the resource type, i.e. these types of the
        resources can be allocated by the pool, e.g. A nfs pool can allocate
        the 'volume' type resources
        """
        raise NotImplementedError

    def create_object(self):
        pass

    def destroy_object(self):
        pass

    def create_resource_object(self, resource_config):
        """
        Create a resource object, no real resource allocated
        """
        meta = resource_config["meta"]
        res_cls = self.get_resource_class(meta["type"])
        res = res_cls(resource_config)
        res.create_object()
        self.resources[res.resource_id] = res
        return res.resource_id

    def destroy_resource_object(self, resource_id):
        """
        Destroy the resource object, all its backings should be released
        """
        resource = self.resources.pop(resource_id)
        resource.destroy_object()

    def clone_resource(self, resource_id):
        resource = self.resources.get(resource_id)
        cloned_resource = resource.clone()
        self.resources[cloned_resource.resource_id] = cloned_resource

        return clone.resource_id

    def update_resource(self, resource_id, config):
        resource = self.resources.get(resource_id)
        cmd, arguments = config.popitem()

        # "nodes" should be the tags defined in the param "nodes"
        node_tags = arguments.pop("nodes", list())
        if node_tags:
            # Check if the node can access the resource pool
            node_names = [cluster.get_node_by_tag(t).name for t in node_tags]
            if not set(node_names).issubset(set(self.attaching_nodes)):
                raise ValueError(
                    f"Not all nodes({node_names}) can access the pool {self.pool_id}"
                )
            # Update the arguments with node names
            arguments["nodes"] = node_names

        handler = resource.get_update_handler(cmd)
        return handler(arguments)

    def get_resource_info(self, resource_id, verbose=False):
        """
        Get the reference of a specified resource
        """
        resource = self.resources.get(resource_id)
        config = deepcopy(resource.resource_config)
        if verbose:
            config["meta"]["pool"] = deepcopy(self.pool_config)

        return config

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
        r, o = node.proxy.resource.get_pool_capability()
        if r != 0:
            raise Exception(o["out"])
    """

    @classmethod
    def get_pool_type(cls):
        return cls._POOL_TYPE
