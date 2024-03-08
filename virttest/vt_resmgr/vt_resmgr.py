import ast
import logging
import os
import pickle

from .resources import get_resource_pool_class

from virttest.vt_cluster import cluster
from virttest.data_dir import get_data_dir


LOG = logging.getLogger("avocado." + __name__)
RESMGR_ENV_FILENAME = os.path.join(get_data_dir(), "vt_resmgr.env")


class _VTResourceManager(object):

    def __init__(self):
        if os.path.isfile(RESMGR_ENV_FILENAME):
            self._pools = self._load()
        else:
            self._pools = dict()  # {pool id: pool object}

    def _load(self):
        with open(RESMGR_ENV_FILENAME, "rb") as f:
            return pickle.load(f)

    def _dump(self):
        with open(RESMGR_ENV_FILENAME, "wb") as f:
            pickle.dump(self.pools, f)

    @property
    def pools(self):
        return self._pools

    def setup(self, all_pools_params):
        """
        Create the pool objects
        """

        LOG.info(f"Setup the resource manager")
        default_pools_nodes = {
            "filesystem": set(),
            # "switch": set(),
        }

        # Register the resource pools
        for category, params in all_pools_params.items():
            for pool_name, pool_params in params.items():
                pool_config = self.define_pool_config(pool_name, pool_params)
                pool_id = self.create_pool_object(pool_config)

                # Record the nodes of the pools with default type, i.e
                # we've pools with default type attached to these nodes
                pool = self.get_pool_by_id(pool_id)
                pool_type = pool.get_pool_type()
                if pool_type in default_pools_nodes:
                    default_pools_nodes[pool_type].update(
                        set(pool.attaching_nodes)
                    )

        # Register the default pools if they are not configured by user
        all_nodes = set([n.name for n in cluster.get_all_nodes()])
        for pool_type, node_set in default_pools_nodes.items():
            for node_name in all_nodes.difference(node_set):
                LOG.debug(f"Register a default {pool_type} pool "
                          "with access nodes {node_name}")
                pool_class = get_resource_pool_class(pool_type)
                pool_config = pool_class.define_default_config()
                pool_config["meta"]["access"]["nodes"] = [node_name]
                self.create_pool_object(pool_config)

        self._dump()

    def cleanup(self):
        LOG.info(f"Cleanup the resource manager")
        if os.path.exists(RESMGR_ENV_FILENAME):
            os.unlink(RESMGR_ENV_FILENAME)

    def startup(self):
        LOG.info(f"Startup the resource manager")
        for pool_id in self.pools:
            self.attach_pool(pool_id)

    def teardown(self):
        LOG.info(f"Teardown the resource manager")
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

    def select_pool(self, resource_type, resource_params):
        """
        Select the resource pool by its cartesian params

        :param resource_type: The resource's type, supported:
                              "volume"
        :type resource_type: string
        :param resource_params: The resource's specific params, e.g.
                                params.object_params('image1')
        :type resource_params: dict or Param
        :return: The resource pool id
        :rtype: string
        """
        LOG.info(f"Select a pool for the {resource_type} resource")
        for pool_id, pool in self.pools.items():
            if pool.meet_resource_request(resource_type, resource_params):
                return pool_id
        return None

    def define_pool_config(self, pool_name, pool_params):
        pool_class = get_resource_pool_class(pool_params["type"])
        return pool_class.define_config(pool_name, pool_params)

    def create_pool_object(self, pool_config):
        pool_type = pool_config["meta"]["type"]
        pool_class = get_resource_pool_class(pool_type)
        pool = pool_class(pool_config)
        pool.create()
        self._pools[pool.pool_id] = pool
        LOG.info(f"Create the pool object {pool.pool_id} for {pool.pool_name}")
        return pool.pool_id

    def destroy_pool_object(self, pool_id):
        """
        The pool should be detached from all worker nodes
        """
        LOG.info(f"Destroy the pool object {pool_id}")
        pool = self.pools.pop(pool_id)
        pool.destroy()

    def attach_pool_to(self, pool, node):
        """
        Attach a pool to a specific node
        """
        LOG.info(f"Attach resource pool ({pool.pool_name}) to {node.name}")
        r, o = node.proxy.resource.connect_pool(pool.pool_id, pool.pool_config)
        if r != 0:
            raise Exception(o["out"])

    def attach_pool(self, pool_id):
        pool = self.get_pool_by_id(pool_id)
        for node_name in pool.attaching_nodes:
            node = cluster.get_node(node_name)
            self.attach_pool_to(pool, node)

    def detach_pool_from(self, pool, node):
        """
        Detach a pool from a specific node
        """
        LOG.info(f"Detach resource pool({pool.pool_name}) from {node.name}")
        r, o = node.proxy.resource.disconnect_pool(pool.pool_id)
        if r != 0:
            raise Exception(o["out"])

    def detach_pool(self, pool_id):
        pool = self.get_pool_by_id(pool_id)
        for node_name in pool.attaching_nodes:
            node = cluster.get_node(node_name)
            self.detach_pool_from(pool, node)

    def query_pool(self, pool_id, request):
        """
        Query the pool's configuration
        """
        pool = self.get_pool_by_id(pool_id)
        return pool.query(request)

    def pool_capability(self, pool_id):
        pool = self.get_pool_by_id(pool_id)
        return pool.capability


vt_resmgr = _VTResourceManager()
