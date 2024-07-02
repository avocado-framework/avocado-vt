import os
import logging
import pickle

from .resources import get_resource_pool_class

from virttest.vt_cluster import cluster
from virttest.data_dir import get_base_backend_dir


LOG = logging.getLogger("avocado." + __name__)


class _VTResourceManager(object):

    def __init__(self):
        self._filename = os.path.join(get_base_backend_dir(), "resmgr.env")
        if os.path.isfile(self._filename):
            data = self._load()
            self._pools = data.get("_pools")
        else:
            self._pools = dict()  # {pool id: pool object}

    def _load(self):
        with open(self._filename, "rb") as f:
            return pickle.load(f).get("data", {})

    def _dump(self):
        data = {"data": self.__dict__}
        with open(self._filename, "wb") as f:
            pickle.dump(data, f)

    @property
    def pools(self):
        return self._pools

    def setup(self, pools_params):
        pool_nodes = {"storage": set()}
        default_pool_types = {"storage": "filesystem"}

        for category, params in pools_params.items():
            # Register the configured pools and attach them to the worker nodes
            for pool_name, pool_params in params.items():
                pool_config = self.define_pool_config(pool_name, pool_params)
                pool = self.get_pool_by_name(pool_name)
                if pool is not None:
                    LOG.debug(f"Pool {pool_name} existed, update its config")
                    pool.update_config(pool_config)
                else:
                    LOG.debug(f"Register the resource pool {pool_name}")
                    self.register_pool(pool_config)

            if category in pool_nodes:
                for node_list in [p["access"]["nodes"] for p in params.values()]:
                    if node_list:
                        pool_nodes[category].update(set(node_list))

        # Register the default pools if they are not configured
        all_nodes = set([n.name for n in cluster.get_all_nodes()])
        for category, node_set in pool_nodes.items():
            if "*" in node_set:
                break

            pool_type = default_pool_types[category]
            pool_class = get_resource_pool_class(pool_type)
            for node_name in all_nodes.difference(node_set):
                LOG.debug(f"Register the default '{pool_type}' pool on {node_name}")
                pool_config = pool_class.define_default_config()
                pool_config["meta"]["access"]["nodes"] = [node_name]
                self.register_pool(pool_config)

        self._dump()

    def cleanup(self):
        if self.pools:
            self._dump()
        else:
            os.unlink(self._filename)

    def startup(self):
        LOG.info(f"Start the resource manager")
        for pool_id in self.pools:
            self.attach_pool(pool_id)

    def teardown(self):
        LOG.info(f"Stop the resource manager")
        for pool_id in list(self.pools.keys()):
            self.detach_pool(pool_id)

    def get_pool_by_name(self, pool_name):
        pools = [p for p in self.pools.values() if p.pool_name == pool_name]
        return pools[0] if pools else None

    def get_pool_by_id(self, pool_id):
        return self.pools.get(pool_id)

    def get_pool_by_resource(self, resource_id):
        pools = [p for p in self.pools.values() if resource_id in p.resources]
        return pools[0] if pools else None

    def select_pool(self, resource_type, resource_params, node_tags):
        """
        Select the resource pool by its cartesian params

        :param resource_type: The resource's type, supported:
                              "volume"
        :type resource_type: string
        :param resource_params: The resource's specific params, e.g.
                                params.object_params('image1')
        :type resource_params: dict or Param
        :param node_tags: A resource pool can be accessed by one or more
                          worker nodes, give the nodes' tag names
        :type node_tags: a list of string
        :return: The resource pool id
        :rtype: string
        """
        node_name_set = set()
        for tag in node_tags:
            node = cluster.get_node_by_tag(tag)
            node_name_set.add(node.name)

        LOG.info(f"Select pool on nodes({node_name_set})")
        for pool_id, pool in self.pools.items():
            if not set(pool.attaching_nodes).issuperset(node_name_set):
                continue
            LOG.info(f"Pool on nodes({pool.attaching_nodes})")
            if pool.meet_resource_request(resource_type, resource_params):
                return pool_id
        return None

    def define_pool_config(self, pool_name, pool_params):
        pool_class = get_resource_pool_class(pool_params["type"])
        return pool_class.define_config(pool_name, pool_params)

    def register_pool(self, pool_config):
        pool_type = pool_config["meta"]["type"]
        pool_class = get_resource_pool_class(pool_type)
        pool = pool_class(pool_config)
        self._pools[pool.pool_id] = pool
        return pool.pool_id

    def unregister_pool(self, pool_id):
        """
        The pool should be detached from all worker nodes
        """
        self.pools.pop(pool_id)

    def attach_pool_to(self, pool, node):
        """
        Attach a pool to a specific node
        """
        LOG.info(f"Attach '{pool.pool_name}' to '{node.name}'")
        node.proxy.resource.connect_pool(pool.pool_id, pool.pool_config)

    def attach_pool(self, pool_id):
        pool = self.get_pool_by_id(pool_id)
        for node_name in pool.attaching_nodes:
            node = cluster.get_node(node_name)
            self.attach_pool_to(pool, node)

    def detach_pool_from(self, pool, node):
        """
        Detach a pool from a specific node
        """
        LOG.info(f"Detach '{pool.pool_name}' from '{node.name}'")
        node.proxy.resource.disconnect_pool(pool.pool_id)
        if pool.is_attached():
            raise

    def detach_pool(self, pool_id):
        pool = self.get_pool_by_id(pool_id)
        for node_name in pool.attaching_nodes:
            node = cluster.get_node(node_name)
            self.detach_pool_from(pool, node)

    def info_pool(self, pool_id):
        """
        Get the pool's information, including 'meta' and 'spec':
        meta:
          e.g. version for tdx, 1.0 or 1.5
        spec:
          common specific attributes
            e.g. nfs_server for nfs pool
          node-specific attributes
            e.g. [node1:{path:/mnt1,permission:rw}, node2:{}]
        """
        info = dict()
        pool = self.get_pool_by_id(pool_id)
        info.update(pool.pool_config)
        for node_name in pool.attaching_nodes:
            node = cluster.get_node(node_name)
            access_info = node.proxy.resource.get_pool_connection(pool_id)
            info.update(access_info)

    def pool_capability(self, pool_id):
        pool = self.get_pool_by_id(pool_id)
        return pool.capability


vt_resmgr = _VTResourceManager()
