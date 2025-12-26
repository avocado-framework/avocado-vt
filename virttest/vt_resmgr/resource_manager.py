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


class PoolBusy(Exception):
    def __str__(self):
        return "The pool is still in use"


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
        The resource manager follows a process-per-test execution model where each test
        case runs in its own process. When a new test process starts, this constructor
        reconstructs the resource manager state by loading the persisted configuration
        from vt_resmgr.env file.

        Note: This per-process approach ensures test isolation while maintaining
        consistent resource state across the distributed cluster environment.
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
                LOG.debug(f"Register a default {def_pool_type} pool on {node_name}")
                pool_config = pool_class.define_default_config([node_name])
                pool = pool_class(pool_config)
                self.pools[pool.uuid] = pool

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
                LOG.debug(f"Register the pool {pool_name}")
                pool_id = self.create_pool_from_params(pool_name, pool_params)
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
        when constructing the resource manager object

        :param resource_pools_params: User defined resource pools' params
        :type resource_pools_params: dict
        """
        LOG.debug(f"Setup the cluster resource manager")

        # TODO: We don't have an env level cleanup, so we have to do it here
        self.cleanup()
        self._register_pools(resource_pools_params)
        # Dump all the configuration for the job process
        self._dump()

    def cleanup(self):
        LOG.debug(f"Cleanup the cluster resource manager")
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
        LOG.debug(f"Startup the cluster resource manager")
        for node in cluster.get_all_nodes():
            node.proxy.resource.start_resource_backing_service()

        for pool_id in self.pools:
            self.attach_pool(pool_id)

        # The pool's status could change after being attached to worker nodes
        self._dump()

    def teardown(self):
        """
        Disconnect all configured resource pools from the accessing nodes

        Note: This function is called only once in job's post_tests
        """
        LOG.debug(f"Teardown the cluster resource manager")
        for pool_id in self.pools:
            self.detach_pool(pool_id)

        for node in cluster.get_all_nodes():
            node.proxy.resource.stop_resource_backing_service()

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
        LOG.debug(f"Select a resource pool for the {resource_type} type resource")
        for pool_id, pool in self.pools.items():
            if pool.meet_resource_request(resource_type, resource_params):
                return pool_id
        return None

    def create_pool_from_params(self, pool_name, pool_params):
        """
        Create a resource pool object.
        Note the resource pools have already been ready to use, avocado-vt
        just accesses the pools, it will not manage them.

        :param pool_name: The unique resource pool name
        :type pool_name: string
        :param pool_params: The resource pool's specific params
        :type pool_params: Param
        :return: The resource pool uuid
        :rtype: string
        """
        LOG.debug(f"Create the pool object of {pool_name} from cartesian params")
        pool_class = get_pool_class(pool_params["type"])
        if pool_class is None:
            raise UnknownPoolType(pool_params["type"])

        # The pool can be accessed by all worker nodes if nodes is not set
        config = pool_class.define_config(pool_name, pool_params)
        if not config["meta"]["access"].get("nodes"):
            config["meta"]["access"]["nodes"] = [
                n.name for n in cluster.get_all_nodes()
            ]

        pool = pool_class(config)
        self.pools[pool.uuid] = pool
        return pool.uuid

    def destroy_pool(self, pool_id):
        """
        Destroy a resource pool object.
        All connections to the pool from the worker nodes should be closed
        before destroying it.

        :param pool_id: The resource pool's uuid
        :type pool_id: string
        """
        pool = self.pools.get(pool_id)
        LOG.debug(f"Destroy the pool object of {pool.name}")
        if pool.connected_nodes:
            raise PoolBusy()
        self.pools.pop(pool_id)

    def attach_pool(self, pool_id):
        """
        Attach the pool to all its accessible worker nodes.
        Note the pool should be ready for use before testing, e.g. for a nfs
        pool, the nfs server should be started and the dirs should be exported
        before running a test, currently avocado-vt doesn't support managing the
        resource pools, it just accesses them.

        :param pool_id: The uuid of the pool to attach
        :type pool_id: string
        """
        pool = self._get_pool_by_id(pool_id)

        LOG.debug(f"Attach the pool {pool.name} to {pool.accessing_nodes}")
        for node_name in pool.accessing_nodes:
            node = cluster.get_node(node_name)
            pool.attach_to(node)

    def detach_pool(self, pool_id):
        """
        Detach the pool from all its accessible worker nodes.

        :param pool_id: The uuid of the pool to detach
        :type pool_id: string
        """
        pool = self._get_pool_by_id(pool_id)

        LOG.debug(f"Detach the pool {pool.name} from {pool.accessing_nodes}")
        for node_name in pool.accessing_nodes:
            node = cluster.get_node(node_name)
            pool.detach_from(node)

    def get_pool_info(self, pool_id, request=None):
        """
        Get the configuration of a specified resource pool.

        The pool's configuration will not be updated automatically, when
        considering the pool capacity in future, it is changeable
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

        LOG.debug(f"Get the resource pool info of {pool.name}")
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

    def _define_resource_config(self, resource_name, resource_type, resource_params):
        """
        Define a resource's configuration by its cartesian params.
        TODO: There will be a converter which is responsible for converting
              the cartesian params to configurations.
        """
        pool_id = self.select_pool(resource_type, resource_params)
        if pool_id is None:
            raise PoolNotAvailable()
        pool = self._get_pool_by_id(pool_id)

        LOG.debug(
            f"Define the resource configuration of {resource_name} by pool {pool.name}"
        )
        res_cls = pool.get_resource_class(resource_type)
        config = res_cls.define_config(resource_name, resource_params)
        config["meta"].update(
            {
                "pool": pool.uuid,
            }
        )
        return config

    def create_resource_from_params(
        self, resource_name, resource_type, resource_params
    ):
        """
        Create a resource object by its cartesian params.
        Note the resource is *NOT* allocated. The resource type cannot be
        retrieved by its params currently, so set it explicitly.

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
        :return: The resource object uuid
        :rtype: string
        """
        resource_config = self._define_resource_config(
            resource_name, resource_type, resource_params
        )
        pool_id = resource_config["meta"]["pool"]
        pool = self._get_pool_by_id(pool_id)
        return pool.create_resource_object(resource_config)

    def create_resource_from_source(self, source_resource_id, target_pool_id=None):
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
        source_resource = pool.resources.get(source_resource_id)
        target_pool = self._get_pool_by_id(target_pool_id) if target_pool_id else pool

        LOG.debug(
            f"Create a resource object from resource {source_resource.name} in pool {target_pool.name}"
        )
        res_cls = target_pool.get_resource_class(source_resource.type)
        if not res_cls:
            raise ValueError(
                f"The target pool {target_pool.name} doesn't support a "
                f"{source_resource.type} type resource"
            )

        resource_config = source_resource.define_config_by_self()
        resource_config["meta"]["pool"] = target_pool.uuid
        return target_pool.create_resource_object(resource_config)

    def destroy_resource(self, resource_id):
        """
        Destroy the resource object, the resource should be released first.

        :param resource_id: The resource uuid
        :type resource_id: string
        """
        pool = self._get_pool_by_resource(resource_id)
        return pool.destroy_resource_object(resource_id)

    def bind_resource(self, resource_id, node_names=None):
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
            pool.check_nodes_accessible(nodes)
        else:
            nodes = [
                n for n in cluster.partitions[0].nodes if n.name in pool.accessing_nodes
            ]
        pool.bind_resource_object(resource_id, nodes)

    def unbind_resource(self, resource_id, node_names=None):
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
        if nodes:
            pool.check_nodes_accessible(nodes)
        pool.unbind_resource_object(resource_id, nodes)

    def get_resource_binding_nodes(self, resource_id):
        """
        Get the binding node names for a specified resource.
        These node names are defined in the param 'nodes'.
        The resource can only be accessed from these binding nodes.

        :param resource_id: The resource uuid.
        :type resource_id: string
        :return: The node names.
        :rtype: list
        """
        pool = self._get_pool_by_resource(resource_id)
        return pool.get_resource_binding_nodes(resource_id)

    def get_resource_info(self, resource_id, request=None):
        """
        Get the configuration of a specified resource.
        Note the configuration may *NOT* be up-to-date, to get the latest,
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

    def clone_resource(self, source_resource_id, arguments=None):
        """
        Clone a new resource from the specified one.
        Note the cloned resource should be allocated in the same resource pool
        with the source's, and it will be allocated.

        :param source_resource_id: The source resource uuid
        :type source_resource_id: string
        :param arguments: The arguments that how to clone the resource:
                  'node': The node name, defined in 'nodes', i.e. the clone
                          will be run on the node. If it's not set, choose the
                          node of its first binding.
                          Note use a single node because there is no use case
                          that needs to run clone on more than one node
        :type arguments: dict
        :return: The cloned resource object uuid
        :rtype: string
        """
        node_name = arguments.pop("node", None) if arguments else None
        node = self._get_nodes([node_name])[0] if node_name else None
        pool = self._get_pool_by_resource(source_resource_id)
        if node:
            pool.check_nodes_accessible([node])
        return pool.clone_resource(source_resource_id, arguments, node)

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
                          node of its first binding.
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
        if node:
            pool.check_nodes_accessible([node])
        return pool.update_resource(resource_id, command, arguments, node)


resmgr = _VTResourceManager()
