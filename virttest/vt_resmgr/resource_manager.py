import logging
import os
import pickle

from virttest.data_dir import get_data_dir
from virttest.vt_cluster import cluster

from .resources import get_resource_pool_class

LOG = logging.getLogger("avocado." + __name__)
RESMGR_ENV_FILENAME = os.path.join(get_data_dir(), "vt_resmgr.env")


class PoolNotFound(Exception):
    def __init__(self, pool_id):
        self._pool_id = pool_id

    def __str__(self):
        pool_id = self._pool_id
        return f"Cannot find the pool by id={pool_id}"


class UnknownPoolType(Exception):
    def __init__(self, pool_type):
        self._pool_type = pool_type

    def __str__(self):
        pool_type = self._pool_type
        return f"Unknown pool type {pool_type}"


class PoolNotAvailable(Exception):
    pass


class ResourceNotFound(Exception):
    pass


class ResourceBusy(Exception):
    pass


class ResourceNotAvailable(Exception):
    pass


class UnknownResourceType(Exception):
    pass


class _VTResourceManager(object):
    def __init__(self):
        """
        When the job starts a new process to run a case, the resource manager
        will be re-constructed as a new object, it reads the dumped file to get
        back all the information. Note the resmgr here is a 'slice' because
        this resmgr only serves the current test case, when the process(test
        case) is finished, the slice resmgr is gone
        """
        self._pools = dict()  # {pool id: pool object}
        if os.path.isfile(RESMGR_ENV_FILENAME):
            self._load()

    @property
    def _dump_data(self):
        return {
            "pools": self.pools,
        }

    @_dump_data.setter
    def _dump_data(self, data):
        self.pools = data.get("pools", dict())

    def _load(self):
        with open(RESMGR_ENV_FILENAME, "rb") as f:
            self._dump_data = pickle.load(f)

    def _dump(self):
        with open(RESMGR_ENV_FILENAME, "wb") as f:
            pickle.dump(self._dump_data, f)

    @property
    def pools(self):
        return self._pools

    @pools.setter
    def pools(self, pools):
        self._pools = pools

    def setup(self, resource_pools_params):
        """
        Register all the resource pools configured in cluster.json
        Note: This function will be called only once during the VT bootstrap

        :param resource_pools_params: User defined resource pools' params
        :type resource_pools_params: dict
        """
        LOG.info(f"Setup the resource manager")

        # FIXME: We don't have an env level cleanup, so we have
        # to do the cleanup at the very beginning of setup
        self.cleanup()

        # Register a default pool on a node where no pool is defined
        # e.g. if no filesystem pool is defined by user, we need to
        # register a default filesystem pool even when user defined
        # a nfs pool
        default_pools_nodes = {
            "filesystem": set(),
            # "switch": set(),
        }

        # Register the resource pools
        for category, params in resource_pools_params.items():
            for pool_name, pool_params in params.items():
                pool_config = self.define_pool_config(pool_name, pool_params)
                pool_id = self.create_pool_object(pool_config)

                # Record the nodes of the pools with default type, i.e
                # we've pools with default type attached to these nodes
                pool = self.get_pool_by_id(pool_id)
                pool_type = pool.get_pool_type()
                if pool_type in default_pools_nodes:
                    default_pools_nodes[pool_type].update(set(pool.attaching_nodes))

        # Register the default resource pools if they are not defined
        all_nodes = set([n.name for n in cluster.get_all_nodes()])
        for pool_type, node_set in default_pools_nodes.items():
            for node_name in all_nodes.difference(node_set):
                LOG.debug(
                    f"Register a default {pool_type} pool "
                    "with access nodes {node_name}"
                )
                pool_class = get_resource_pool_class(pool_type)
                pool_config = pool_class.define_default_config()
                pool_config["meta"]["access"]["nodes"] = [node_name]
                self.create_pool_object(pool_config)

        # Dump all the information for the job process
        self._dump()

    def cleanup(self):
        LOG.info(f"Cleanup the resource manager")

        if os.path.exists(RESMGR_ENV_FILENAME):
            os.unlink(RESMGR_ENV_FILENAME)
        self.pools = dict()

    def startup(self):
        """
        Attach all configured resource pools
        Note: This function is called only once in job's pre_tests
        """
        LOG.info(f"Startup the resource manager")

        for node in cluster.get_all_nodes():
            node.proxy.resource.startup_resbacking_mgr()

        for pool_id in self.pools:
            self.attach_pool(pool_id)

    def teardown(self):
        """
        Detach all configured resource pools
        Note: This function is called only once in job's post_tests
        """
        LOG.info(f"Teardown the resource manager")
        for pool_id in self.pools:
            self.detach_pool(pool_id)

        for node in cluster.get_all_nodes():
            node.proxy.resource.teardown_resbacking_mgr()

    def get_pool_by_name(self, pool_name):
        pools = [p for p in self.pools.values() if p.pool_name == pool_name]
        return pools[0] if pools else None

    def get_pool_by_id(self, pool_id):
        return self.pools.get(pool_id)

    def get_pool_by_resource(self, resource_id):
        pools = [p for p in self.pools.values() if resource_id in p.resources]
        return pools[0] if pools else None

    def select_pool(self, resource_type, resource_params)
        """
        Select the resource pool for a specified type of resource

        :param resource_type: The resource type, it can be implied, e.g.
                              the image's storage resource is a "volume",
                              supported: "volume"
        :type resource_type: string
        :param resource_params: The resource's specific params, it can be
                                defined by an upper-level object, e.g.
                                "image1" has a storage volume resource, so
                                  resource_params = subset of image1's params
        :type resource_params: Param or dict
        :return: The resource pool id
        :rtype: string
        """
        LOG.info(f"Select a resource pool with conditions")
        for pool_id, pool in self.pools.items():
            # Check if the pool can support a specific resource type
            if not pool.get_resource_class(resource_type):
                continue
            if pool.meet_conditions(resource_params):
                return pool_id
        return None

    def define_pool_config(self, pool_name, pool_params):
        """
        Define a resource pool's configuration by its cartesian params

        :param pool_name: The uniq resource pool name, defined in cluster.json
        :type pool_name: string
        :param pool_params: The resource pool's specific params
        :type pool_params: Param
        :return: The resource pool's configuration,
                 format: {"meta":{...}, "spec":{...}}
                 The specific attributes depend on the specific pool
        :rtype: dict
        """
        pool_class = get_resource_pool_class(pool_params["type"])
        if pool_class is None:
            raise UnknownPoolType(pool_params["type"])

        return pool_class.define_config(pool_name, pool_params)

    def create_pool_object(self, pool_config):
        """
        Create a resource pool object

        :param pool_config: The pool's configuration, generated by
                            define_pool_config function
        :type pool_config: dict
        :return: The resource pool id
        :rtype: string
        """
        pool_type = pool_config["meta"]["type"]
        pool_class = get_resource_pool_class(pool_type)
        if pool_class is None:
            raise UnknownPoolType(pool_type)

        pool = pool_class(pool_config)
        pool.create_object()
        self.pools[pool.pool_id] = pool

        LOG.info(f"Create the pool object {pool.pool_id} for {pool.pool_name}")
        return pool.pool_id

    def destroy_pool_object(self, pool_id):
        """
        Destroy a resource pool object
        Note the pool should be stopped before the destroying

        :param pool_id: The id of the pool
        :type pool_id: string
        """
        LOG.info(f"Destroy the pool object {pool_id}")
        pool = self.pools.pop(pool_id)
        pool.destroy_object()

    def _attach_pool_to(self, pool, node):
        """
        Attach a pool to a specific node
        """
        LOG.info(f"Attach resource pool ({pool.pool_name}) to {node.name}")
        r, o = node.proxy.resource.connect_pool(pool.pool_id, pool.customize_pool_config(node.name))
        if r != 0:
            raise Exception(o["out"])

    def attach_pool(self, pool_id):
        """
        Attach the pool to the worker nodes, where the pool can be accessed
        Note the user should make the pool ready for use before testing, e.g
        for a nfs pool, the user should start nfs server and export dirs

        :param pool_id: The id of the pool to attach
        :type pool_id: string
        """
        pool = self.get_pool_by_id(pool_id)
        for node_name in pool.attaching_nodes:
            node = cluster.get_node(node_name)
            self._attach_pool_to(pool, node)

    def _detach_pool_from(self, pool, node):
        """
        Detach a pool from a specific worker node
        """
        LOG.info(f"Detach resource pool({pool.pool_name}) from {node.name}")
        r, o = node.proxy.resource.disconnect_pool(pool.pool_id)
        if r != 0:
            raise Exception(o["out"])

    def detach_pool(self, pool_id):
        """
        Detach the pool from the worker nodes

        :param pool_id: The id of the pool to detach
        :type pool_id: string
        """
        pool = self.get_pool_by_id(pool_id)
        for node_name in pool.attaching_nodes:
            node = cluster.get_node(node_name)
            self._detach_pool_from(pool, node)

    def get_pool_info(self, pool_id, request=None, verbose=False):
        """
        Get the configuration of a specified resource pool

        :param pool_id: The resource pool id
        :type pool_id: string
        :param request: The query content, format:
                          None
                          meta[.<key>]
                          spec[.<key>]
                        Note return the whole configuration if request=None
        :type request: string
        :return: The pool's configuration, e.g request=meta.type, it
                 returns: {"type": "filesystem"}
        :rtype: dict
        """
        pool = self.get_pool_by_id(pool_id)
        return pool.get_info(verbose)

    def define_resource_config(self, resource_name, resource_type, resource_params):
        """
        Define a resource's configuration by its cartesian params.

        :param resource_name: The resource name
        :type resource_name: string
        :param resource_type: The resource type, it can be implied, e.g.
                              the image's storage resource is a "volume",
                              supported: "volume"
        :type resource_type: string
        :param resource_params: The resource's specific params, it can be
                                defined by an upper-level object, e.g.
                                "image1" has a storage volume resource, so
                                  resource_params = subset of image1's params
        :type resource_params: Param or dict
        :return: The resource's configuration:
                   {"meta":{...}, "spec":{...}}
                 Different resources return different configurations
        :rtype: dict
        """
        pool_id = self.select_pool(resource_type, resource_params)
        if pool_id is None:
            raise PoolNotAvailable()
        pool = self.get_pool_by_id(pool_id)
        return pool.define_resource_config(
            resource_name, resource_type, resource_params
        )

    def clone_resource(self, resource_id):
        """
        Clone a new resource from the specified one.
        Note the cloned resource should be allocated.

        :param resource_id: The source resource uuid
        :type resource_id: string
        :param poo_id: The new resource's pool uuid
        :type resource_id: string
        :return: The cloned resource object uuid
        :rtype: string
        """
        pool = self.get_pool_by_resource(resource_id)
        return pool.clone_resource(resource_id)

    def create_resource_object_from(self, resource_id, pool_id=None):
        """
        Create a new resource object from an existing resource object.
        The pool needs NOT be the same one where the resource comes from

        :param resource_id: The source resource uuid
        :type resource_id: string
        :param poo_id: The new resource's pool uuid
        :type resource_id: string
        :return: The new resource object uuid
        :rtype: string
        """
        pool = self.get_pool_by_resource(resource_id)
        resource = pool.resources.get(resource_id)
        target_pool = self.get_pool_by_id(pool_id) if pool_id else pool
        return target_pool.create_resource_object_from(resource)

    def create_resource_object(self, resource_config):
        """
        Create a resource object without any specific resource allocation.
        We cannot bind the backing in this function because we can unbind
        a resource from all its backings, then bind it to another backing
        on another worker node.

        :param resource_config: The resource configuration, generated by
                                define_resource_config function
        :type resource_config: dict
        :return: The resource uuid
        :rtype: string
        """
        pool_id = resource_config["meta"]["pool"]
        pool = self.get_pool_by_id(pool_id)
        if pool is None:
            raise PoolNotFound(pool_id)
        return pool.create_resource_object(resource_config)

    def destroy_resource_object(self, resource_id):
        """
        Destroy the resource object, the specific resource allocation
        will be released

        :param resource_id: The resource id
        :type resource_id: string
        """
        pool = self.get_pool_by_resource(resource_id)
        pool.destroy_resource_object(resource_id)

    def get_resource_info(self, resource_id, request=None, verbose=False):
        """
        Get the configuration of a specified resource

        :param resource_id: The resource id
        :type resource_id: string
        :param request: The query content, format:
                          None
                          meta[.<key>]
                          spec[.<key>]
                        Examples:
                          meta
                          spec.size
        :type request: string
        :param verbose: True to get the resource pool's configuration, while
                        False to get the resource pool's uuid
        :type verbose: boolean
        :return: The resource's configuration, e.g request="spec.size", it
                 returns: {"size": "123456"}
        :rtype: dict
        """
        pool = self.get_pool_by_resource(resource_id)
        config = pool.get_resource_info(resource_id, verbose)

        if request is not None:
            for item in request.split("."):
                if item in config:
                    config = config[item]
                else:
                    raise ValueError(request)
            else:
                config = {item: config}

        return config

    def clone_resource(self, resource_id):
        """
        Clone a resource from the specified one
        Note the new resource will be allocated from the same resource pool

        :param resource_id: The resource object uuid
        :type resource_id: string
        :return: The new resource uuid
        :rtype: string
        """
        pool = self.get_pool_by_resource(resource_id)
        return pool.clone_resource(resource_id)

    def update_resource(self, resource_id, config):
        """
        Update a resource, the config format:
          {'command': arguments}
        Supported commands:
          'bind': Bind a specified resource to one or more worker nodes in order
                  to access the specific resource allocation, note the resource
                  is *NOT* allocated with the bind command
          'unbind': Unbind a specified resource from one or more worker nodes,
                    the specific resource will be released only when all bindings
                    are gone
          'allocate': Allocate the resource
          'release': Release the resource
          'sync': Sync up the resource configuration. Some items of the
                  configuration can change and only be fetched on the worker
                  nodes, e.g. allocation, use sync to sync-up these items
        The arguments is a dict object which contains all related settings for a
        specific action, common arguments:
          "nodes": List of node tags defined in the cartesian param "nodes", it
                   means the action will be taken across these nodes

        Examples:
          Bind a resource to one or more nodes
            {'bind': {'nodes': ['node1']}}
            {'bind': {'nodes': ['node1', 'node2']}}
          Unbind a resource from one or more nodes
            {'unbind': {'nodes': []}}
            {'unbind': {'nodes': ['node1']}}
          Allocate the resource
            {'allocate': {}}
          Release the resource
            {'release': {}}

        :param resource_id: The resource id
        :type resource_id: string
        :param config: The specified action and its arguments
        :type config: dict
        """
        pool = self.get_pool_by_resource(resource_id)
        return pool.update_resource(resource_id, config)


resmgr = _VTResourceManager()
