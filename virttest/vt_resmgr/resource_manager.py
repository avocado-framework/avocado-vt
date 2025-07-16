# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2025
# Authors: Zhenchao Liu <zhencliu@redhat.com>

import logging
import os
import pickle

from virttest.data_dir import get_data_dir
from virttest.vt_cluster import cluster

from .resources import get_pool_class

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
    def __str__(self):
        return "Cannot find available pools"


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
        back all the information. Note the resmgr here only serves the current
        test case, when the process(test case) is finished, the resmgr is gone
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

        Note: This function will be called only once during the VT bootstrap.
        Afterward, read the configuration from the RESMGR_ENV_FILENAME file
        when constructing the resmgr object

        :param resource_pools_params: User defined resource pools' params
        :type resource_pools_params: dict
        """
        LOG.info(f"Setup the cluster resource manager")

        # TODO: We don't have an env level cleanup, so we have to do it here
        self.cleanup()

        # Register the default local pools when they are not configured
        #   Storage: the local filesystem pool
        # E.g. Register a local filesystem pool when it's not configured in
        # cluster.json, even though other types of storage pools are configured
        default_pools_nodes = {
            "filesystem": set(),
        }
        # {"storage":{"fs1":{}, "fs2":{}}, "network":{}}
        for _, params in resource_pools_params.items():
            for pool_name, pool_params in params.items():
                pool_config = self.define_pool_config(pool_name, pool_params)
                pool_id = self.create_pool_object(pool_config)

                # The nodes don't need default pools
                pool = self._get_pool_by_id(pool_id)
                pool_type = pool.get_pool_type()
                if pool_type in default_pools_nodes:
                    default_pools_nodes[pool_type].update(set(pool.accessing_nodes))

        # Register the default pools if they are not defined in cluster.json
        # TODO: Currently we only handle the local default pool
        all_nodes = set([n.name for n in cluster.get_all_nodes()])
        for pool_type, node_set in default_pools_nodes.items():
            for node_name in all_nodes.difference(node_set):
                LOG.debug(
                    f"Register a default {pool_type} pool "
                    "with access nodes {node_name}"
                )
                pool_class = get_pool_class(pool_type)
                pool_config = pool_class.define_default_config([node_name])
                self.create_pool_object(pool_config)

        # Dump all the configuration for the job process
        self._dump()

    def cleanup(self):
        LOG.info(f"Cleanup the cluster resource manager")
        if os.path.exists(RESMGR_ENV_FILENAME):
            os.unlink(RESMGR_ENV_FILENAME)
        self.pools = dict()

    def startup(self):
        """
        Attach all configured resource pools to their accessing nodes

        Note: This function is called only once in job's pre_tests, the
        partition is not created yet, it's a cluster level function, i.e.
        do the startup work across all cluster worker nodes
        """
        LOG.info(f"Startup the cluster resource manager")
        for node in cluster.get_all_nodes():
            node.proxy.resource.startup_resbkmgr()

        for pool_id in self.pools:
            self.attach_pool(pool_id)

    def teardown(self):
        """
        Disconnect all configured resource pools from the accessing nodes

        Note: This function is called only once in job's post_tests
        """
        LOG.info(f"Teardown the cluster resource manager")
        for pool_id in self.pools:
            self.detach_pool(pool_id)

        for node in cluster.get_all_nodes():
            node.proxy.resource.teardown_resbkmgr()

    def _get_pool_by_name(self, pool_name):
        pools = [p for p in self.pools.values() if p.pool_name == pool_name]
        return pools[0] if pools else None

    def _get_pool_by_id(self, pool_id):
        return self.pools.get(pool_id)

    def _get_pool_by_resource(self, resource_id):
        pools = [p for p in self.pools.values() if resource_id in p.resources]
        return pools[0] if pools else None

    def select_pool(self, resource_type, resource_params):
        """
        Select the resource pool for a specified type of resource.

        Two ways to select the resource pool:
        1. Specify the xxx_pool_selectors params explicitly (Recommended), e.g.
           nodes = node1 node2
           volume_pool_selectors_base = [{"key": "type", "operator": "==", "values": "nfs"},
           volume_pool_selectors_base += {"key": "access.nodes", "operator": "contains", "values": "node1 node2"},]
           in which 'access.nodes' is the worker nodes where the image base can be accessed
        2. xxx_pool_selectors is not set, avocado-vt will create the default selectors,
           it assumes that all partition nodes can access the pool, why? Because for
           the single node testing, the node must access the pool while for the live
           migration testing, assume the pool should be accessed by all partition nodes.
           Note in this case, it may fail to select the expected resource pools.
        Always use the first way to select the resource pool when possible.

        :param resource_type: The resource type
        :type resource_type: string
        :param resource_params: The resource's specific params
        :type resource_params: Param or dict
        :return: The resource pool id
        :rtype: string
        """
        LOG.info(f"Select a resource pool for the {resource_type} resource")
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
        pool_class = get_pool_class(pool_params["type"])
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
        pool_class = get_pool_class(pool_type)
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
        pool = self.pools.pop(pool_id)
        LOG.info(f"Destroy the pool object {pool_id} for {pool.pool_name}")
        pool.destroy_object()

    def attach_pool(self, pool_id):
        """
        Attach the pool to the accessible worker nodes

        Note the pool should be ready for use before testing, e.g. for a nfs
        pool, the nfs server should be started and the dirs should be exported
        before running a test, currently avocado-vt doesn't support managing the
        resource pools, it just accesses them.

        :param pool_id: The id of the pool to attach
        :type pool_id: string
        """
        pool = self._get_pool_by_id(pool_id)
        for node_name in pool.accessing_nodes:
            node = cluster.get_node(node_name)
            pool.attach(node)

    def detach_pool(self, pool_id):
        """
        Detach the pool from the worker nodes

        :param pool_id: The id of the pool to detach
        :type pool_id: string
        """
        pool = self._get_pool_by_id(pool_id)
        for node_name in pool.accessing_nodes:
            node = cluster.get_node(node_name)
            pool.detach(node)

    def get_pool_info(self, pool_id, request=None):
        """
        Get the configuration of a specified resource pool.

        The pool's configuration will not be updated currently, but when we
        consider the pool capacity in future, it is changeable, e.g. the storage
        pool's free space.
        TODO: Add pool access configuration and pool capacity

        :param pool_id: The resource pool id
        :type pool_id: string
        :param request: The query content, format:
                          None
                          meta[.<key>]
                          spec[.<key>]
                        Note return the whole configuration if request=None
        :type request: string
        :return: The pool's configuration, e.g. request=meta.type, it returns:
                 {"type": "filesystem"}
        :rtype: dict
        """
        pool = self._get_pool_by_id(pool_id)
        config = pool.get_info()

        if request is not None:
            item = ""
            for item in request.split("."):
                if item in config:
                    config = config[item]
                else:
                    raise ValueError(f"Unknown key {item}")
            else:
                config = {item: config}

        return config

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
        :return: The resource's configuration, e.g.
                 {"meta":{...}, "spec":{...}}
                 Different resources return different configurations
        :rtype: dict
        """
        pool_id = self.select_pool(resource_type, resource_params)
        if pool_id is None:
            raise PoolNotAvailable()

        pool = self._get_pool_by_id(pool_id)
        return pool.define_resource_config(
            resource_name, resource_type, resource_params
        )

    def create_resource_object(self, resource_config):
        """
        Create a resource object without any specific resource allocation.

        :param resource_config: The resource configuration, generated by
                                define_resource_config function
        :type resource_config: dict
        :return: The resource uuid
        :rtype: string
        """
        pool_id = resource_config["meta"]["pool"]
        pool = self._get_pool_by_id(pool_id)
        if pool is None:
            raise PoolNotFound(pool_id)
        return pool.create_resource_object(resource_config)

    def create_resource_object_by(self, resource_id, pool_id=None, access_nodes=None):
        """
        Create a new resource object by an existing one.
        Note the pool needs *NOT* to be the same one where the resource is allocated

        :param resource_id: The source resource uuid
        :type resource_id: string
        :param pool_id: The new resource's pool uuid, use the source resource's
                       pool id if it is not set
        :type resource_id: string
        :param access_nodes: The worker node tags defined by 'nodes' where the
                             resource is accessed, use the source resource's
                             access nodes if it's not set
        :type access_nodes: list
        :return: The new resource object uuid
        :rtype: string
        """
        pool = self._get_pool_by_resource(resource_id)
        resource = pool.resources.get(resource_id)
        target_pool = self._get_pool_by_id(pool_id) if pool_id else pool

        if not target_pool.get_resource_class(resource.resource_type):
            raise ValueError(
                f"The pool {target_pool.pool_name} doesn't support a "
                f"{resource.resource_type} resource"
            )

        # Use source resource's access nodes by default
        node_names = resource.resource_binding_nodes
        if access_nodes:
            node_names = [cluster.get_node_by_tag(t).name for t in access_nodes]
            # Check if the pool can be accessed by the access_nodes
            if not set(node_names).issubset(set(target_pool.accessing_nodes)):
                raise ValueError(f"Not all nodes({node_names}) can access the pool")

        return target_pool.create_resource_object_by(resource, node_names)

    def destroy_resource_object(self, resource_id):
        """
        Destroy the resource object, the specific resource allocation
        will be released

        :param resource_id: The resource id
        :type resource_id: string
        """
        pool = self._get_pool_by_resource(resource_id)
        pool.destroy_resource_object(resource_id)

    def get_resource_info(self, resource_id, request=None, verbose=False, sync=False):
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
        :param verbose: True to get the resource pool's configuration
                        False to get the resource pool's uuid
        :type verbose: boolean
        :param sync: True to sync up the resource's configuration, some items
                     may be out of date, e.g. the volume's allocation, then we
                     can do sync-up to get the latest configuration.
                     False not to sync up the resource's configuration, i.e. use
                     the cached configuration
        :type sync: boolean
        :return: The resource's configuration, e.g. request="spec.size", it
                 returns: {"size": "123456"}
        :rtype: dict
        """
        pool = self._get_pool_by_resource(resource_id)
        config = pool.get_resource_info(resource_id, verbose, sync)

        if request is not None:
            item = ""
            for item in request.split("."):
                if item in config:
                    config = config[item]
                else:
                    raise ValueError(request)
            else:
                config = {item: config}

        return config

    def clone_resource(self, resource_id, arguments=None):
        """
        Clone a new resource from the specified one.
        Note the cloned resource should be allocated in the same resource pool.

        :param resource_id: The source resource uuid
        :type resource_id: string
        :param arguments: The arguments that how to clone the resource, e.g.
                          use cp to copy a file based volume by default for
                          a file volume resource, but we can clone it in some
                          other ways: arguments = {"how": "dd"}
        :type arguments: dict
        :return: The cloned resource object uuid
        :rtype: string
        """
        pool = self._get_pool_by_resource(resource_id)
        return pool.clone_resource(resource_id, arguments)

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
          'sync': Sync up the resource configuration, some items of the
                  configuration can change and only be fetched on the worker
                  nodes, e.g. allocation, use sync to sync-up these items.
          'move': Move the resource from one pool to another, it only changes
                  the resource state without creating a new resource object

        The arguments is a dict object which contains all related settings for a
        specific command, common arguments:
          "nodes": List of node tags defined in the cartesian param "nodes",
                   it means the action will be taken across these nodes.

        Examples:
          nodes = 'node1 node2'

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
          Move the resource to another pool, whose id is pool_id, the resource
          should be accessed on the worker node 'node2', if nodes is not set,
          use all the partition nodes
            {'move': {'nodes': ['node2'], 'pool': 'pool_id'}}

        :param resource_id: The resource id
        :type resource_id: string
        :param config: The specified command and its arguments
        :type config: dict
        """
        pool = self._get_pool_by_resource(resource_id)

        # Check if the pool can be accessed by the "nodes"
        cmd, arguments = config.popitem()
        access_nodes = arguments.pop("nodes", list())
        if access_nodes:
            node_names = [cluster.get_node_by_tag(t).name for t in access_nodes]
            if not set(node_names).issubset(set(pool.accessing_nodes)):
                raise ValueError(f"Not all nodes({node_names}) can access the pool")

            # Update the arguments with node names
            arguments["nodes"] = node_names

        return pool.update_resource(resource_id, {cmd: arguments})


resmgr = _VTResourceManager()
