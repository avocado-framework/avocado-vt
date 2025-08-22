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
        return f"Cannot find the pool by uuid={pool_id}"


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
        self._pools = dict()  # {pool uuid: pool object}
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

    @staticmethod
    def _get_nodes(node_names):
        nodes = list()
        for tag in node_names:
            node = cluster.get_node_by_tag(tag)
            if node:
                nodes.append(node)
            else:
                raise ValueError(f"Wrong node name {tag}")
        return nodes

    def _register_default_pool(self, def_pool_type, def_pool_nodes):
        def _register_default_storage_pool():
            pool_class = get_pool_class(def_pool_type)
            for node_name in def_pool_nodes:
                LOG.info(f"Register a default {def_pool_type} pool on {node_name}")
                pool_config = pool_class.define_default_config([node_name])
                self.create_pool_object(pool_config)

        register_funcs = {
            "filesystem": _register_default_storage_pool,
        }
        register_funcs[def_pool_type]()

    def _register_pools(self, pools_params):
        def _update_nodes(def_pool_type, pool_nodes):
            def _update_storage_nodes():
                nodes = default_pools_nodes[def_pool_type]
                default_pools_nodes[def_pool_type] = list(set(nodes) - set(pool_nodes))

            update_funcs = {
                "filesystem": _update_storage_nodes,
            }
            update_funcs[def_pool_type]()

        # Register the default pools when they are not configured
        all_node_names = [n.name for n in cluster.get_all_nodes()]
        default_pools_nodes = {
            "filesystem": all_node_names,
        }

        for _, params in pools_params.items():
            for pool_name, pool_params in params.items():
                LOG.info("Register the pool {pool_name}")
                pool_config = self.define_pool_config(pool_name, pool_params)
                pool_id = self.create_pool_object(pool_config)

                pool = self._get_pool_by_id(pool_id)
                if pool.type in default_pools_nodes:
                    _update_nodes(pool.type, pool.accessing_nodes)

        for pool_type, def_pool_nodes in default_pools_nodes.items():
            self._register_default_pool(pool_type, def_pool_nodes)

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
        self._register_pools(resource_pools_params)
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

        # The pool's status could change after being attached to worker nodes
        self._dump()

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
        pools = [p for p in self.pools.values() if p.name == pool_name]
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
        1. The xxx_pool_selectors params is specified explicitly (Recommended):
           nodes = node1 node2
           volume_pool_selectors_base = [{"key": "type", "operator": "==", "values": "nfs"},
           volume_pool_selectors_base += {"key": "nodes", "operator": "contains", "values": "node1 node2"},]
           in which nodes is the worker nodes, defined by param 'nodes', where
           the resource pool can be accessed
        2. xxx_pool_selectors is *NOT* set, avocado-vt will create the default
           selectors, it uses other params to guess expected pool, e.g. the
           storage_type for the volume resource.
           Note it could fail to select the expected pools in some situations.
        Recommend the first to select the resource pool.

        :param resource_type: The resource type
        :type resource_type: string
        :param resource_params: The resource's specific params
        :type resource_params: Param or dict
        :return: The resource pool uuid
        :rtype: string
        """
        LOG.info(f"Select a resource pool for the {resource_type} type resource")
        for pool_id, pool in self.pools.items():
            if pool.meet_resource_request(resource_type, resource_params):
                return pool_id
        return None

    @staticmethod
    def define_pool_config(pool_name, pool_params):
        """
        Define a resource pool's configuration by the params defined in cluster.json
        Note if the accessing nodes is not set, it means the pool can be accessed by
        all the worker nodes in the cluster.

        :param pool_name: The uniq resource pool name
        :type pool_name: string
        :param pool_params: The resource pool's specific params
        :type pool_params: Param
        :return: The resource pool's configuration,
                 format: {"meta":{...}, "spec":{...}}
                 The specific attributes depend on the specific pool
        :rtype: dict
        """
        LOG.info(f"Define the pool configuration of {pool_name}")
        pool_class = get_pool_class(pool_params["type"])
        if pool_class is None:
            raise UnknownPoolType(pool_params["type"])

        # The pool can be accessed by all worker nodes if nodes is not set
        config = pool_class.define_config(pool_name, pool_params)
        if not config["meta"]["access"].get("nodes"):
            config["meta"]["access"]["nodes"] = [n.name for n in cluster.get_all_nodes()]

        return config

    def create_pool_object(self, pool_config):
        """
        Create a resource pool object.

        :param pool_config: The pool's configuration, generated by
                            define_pool_config function.
        :type pool_config: dict
        :return: The resource pool uuid
        :rtype: string
        """
        LOG.info(f"Create the pool object of {pool_config['meta']['name']}")
        pool_type = pool_config["meta"]["type"]
        pool_class = get_pool_class(pool_type)
        if pool_class is None:
            raise UnknownPoolType(pool_type)

        pool = pool_class(pool_config)
        pool.create_object()
        self.pools[pool.uuid] = pool

        return pool.uuid

    def destroy_pool_object(self, pool_id):
        """
        Destroy a resource pool object.
        Note the pool should be stopped before the destroying.

        :param pool_id: The resource pool's uuid
        :type pool_id: string
        """
        pool = self.pools.pop(pool_id)

        LOG.info(f"Destroy the pool object of {pool.name}")
        return pool.destroy_object()

    def attach_pool(self, pool_id):
        """
        Attach the pool to all its accessing worker nodes

        Note the pool should be ready for use before testing, e.g. for a nfs
        pool, the nfs server should be started and the dirs should be exported
        before running a test, currently avocado-vt doesn't support managing the
        resource pools, it just accesses them.

        :param pool_id: The uuid of the pool to attach
        :type pool_id: string
        """
        pool = self._get_pool_by_id(pool_id)

        LOG.info(f"Attach the pool {pool.name} to {pool.accessing_nodes}")
        for node_name in pool.accessing_nodes:
            node = cluster.get_node(node_name)
            pool.attach(node)

    def detach_pool(self, pool_id):
        """
        Detach the pool from all its accessing worker nodes

        :param pool_id: The uuid of the pool to detach
        :type pool_id: string
        """
        pool = self._get_pool_by_id(pool_id)

        LOG.info(f"Detach the pool {pool.name} from {pool.accessing_nodes}")
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

        :param pool_id: The resource pool uuid
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
        Create a resource object by its configurations.
        Note the resource is *NOT* allocated yet.

        :param resource_config: The resource configuration, generated by
                                define_resource_config function
        :type resource_config: dict
        :return: The resource object uuid
        :rtype: string
        """
        pool_id = resource_config["meta"]["pool"]
        pool = self._get_pool_by_id(pool_id)
        return pool.create_resource_object(resource_config)

    def create_resource_object_from_source(self, source_resource_id, target_pool_id=None):
        """
        Create a new resource object from an existing resource.

        Some configurations should be the same, e.g. for a storage resource,
        the size, type are the same as the source resource, but the
        uri/filename always change in case both are in the same pool.
        Note the resource is *NOT* allocated yet.

        :param source_resource_id: The source resource uuid
        :type source_resource_id: string
        :param target_pool_id: The new resource's pool uuid, use the same pool
                               of the source resource when it is not set
        :type target_pool_id: string
        :return: The new resource object uuid
        :rtype: string
        """
        pool = self._get_pool_by_resource(source_resource_id)
        resource = pool.resources.get(source_resource_id)
        target_pool = self._get_pool_by_id(target_pool_id) if target_pool_id else pool
        return target_pool.create_resource_object_by(resource)

    def destroy_resource_object(self, resource_id):
        """
        Destroy the resource object, the resource should be released first.

        :param resource_id: The resource uuid
        :type resource_id: string
        """
        pool = self._get_pool_by_resource(resource_id)
        return pool.destroy_resource_object(resource_id)

    def bind_resource_object(self, resource_id, node_names=None):
        """
        Bind a specified resource to its backings on the specified worker
        nodes, where the resource can be accessed.

        :param resource_id: The resource uuid
        :type resource_id: string
        :param node_names: The node names defined in the param 'nodes', if it's
                           not set, bind the resource to its backings on the
                           nodes both in the partition and in the pool's
                           accessible nodes
        :type node_names: list
        """
        pool = self._get_pool_by_resource(resource_id)
        if node_names:
            nodes = self._get_nodes(node_names)
        else:
            nodes = [n for n in cluster.get_partition().nodes if n.name in pool.accessing_nodes]
        return pool.bind_resource_object(resource_id, nodes)

    def unbind_resource_object(self, resource_id, node_names=None):
        """
        Unbind a specified resource from its backings on the worker nodes.

        :param resource_id: The resource uuid
        :type resource_id: string
        :param node_names: The node names defined in the param 'nodes', if it's
                           not set, unbind the resource from all its backings.
        :type node_names: list
        """
        nodes = self._get_nodes(node_names) if node_names else list()
        pool = self._get_pool_by_resource(resource_id)
        return pool.unbind_resource_object(resource_id, nodes)

    def get_resource_info(self, resource_id, request=None):
        """
        Get the information of a specified resource.

        Note the information may *NOT* be up-to-date, to get the latest status,
        please sync up the status first:
          resmgr.update_resource(resource_id, "sync")

        :param resource_id: The resource uuid
        :type resource_id: string
        :param request: The query content, format:
                          None
                          meta[.<key>]
                          spec[.<key>]
                        Examples:
                          meta
                          spec.size
        :type request: string
        :return: The resource's configuration, e.g. request="spec.size", it
                 returns: {"size": "123456"}
        :rtype: dict
        """
        pool = self._get_pool_by_resource(resource_id)
        return pool.get_resource_info(resource_id, request)

    def clone_resource(self, resource_id, arguments=None):
        """
        Clone a new resource from the specified one.
        Note the cloned resource should be allocated in the same resource pool.

        :param resource_id: The source resource uuid
        :type resource_id: string
        :param arguments: The arguments that how to clone the resource:
                  'node': The node name, defined in 'nodes', i.e. the clone
                          will be run on the node. If it's not set, choose the
                          first one.
                          Note use a single node because there is no use case
                          that needs to run clone on more than one node
        :type arguments: dict
        :return: The cloned resource object uuid
        :rtype: string
        """
        node_name = arguments.pop("node", None) if arguments else None
        node = self._get_nodes([node_name])[0] if node_name else None
        pool = self._get_pool_by_resource(resource_id)
        return pool.clone_resource(resource_id, arguments, node)

    def update_resource(self, resource_id, command, arguments=None):
        """
        Update a specified resource.

        :param resource_id: The resource object uuid
        :type resource_id: string
        :param command: The command name.
                        The supported commands for all kinds of resources:
              allocate: Allocate a resource.
               release: Release a resource. A resource cannot be released until
                        all its bound nodes are unbound.
                  sync: Sync up the resource configuration, some status of the
                        resource can change, e.g. allocation of a volume, use
                        sync to get the latest status.

                        The supported commands for a file-based volume resource:
                resize: Resize the file-based volume
        :type command: string
        :param arguments: The command's arguments.
                          The supported arguments for all commands:
                  'node': The node name, defined in 'nodes', i.e. the command
                          will be run on the node. If it's not set, choose the
                          first one.
                          Note use a single node because there is no use case
                          that needs to run a command on more than one node
        :type arguments: dict
        :return:
        :rtype:
        Examples: nodes = 'node1 node2'
                  Allocate a resource
                    command = 'allocate', arguments = {}
                  Release a resource on node1
                    command = 'release', arguments = {'node': 'node1'}
        """
        node_name = arguments.pop("node", None) if arguments else None
        node = self._get_nodes([node_name])[0] if node_name else None
        pool = self._get_pool_by_resource(resource_id)
        return pool.update_resource(resource_id, command, arguments, node)


resmgr = _VTResourceManager()
