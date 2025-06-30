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
import uuid
from abc import ABC, abstractmethod
from copy import deepcopy

LOG = logging.getLogger("avocado." + __name__)


class ResourcePool(ABC):
    """
    Abstract base class for resource pools in the VT resource management system.

    A resource pool represents a logical collection of resources (volumes, ports, etc.)
    that can be allocated and managed as a unit. Pools provide isolation, access control,
    and type-specific resource management capabilities. Each pool is associated with
    specific cluster nodes and supports one or more resource types.

    Resource pools serve as the bridge between the abstract resource requests from tests
    and the concrete resource implementations on worker nodes. They coordinate resource
    lifecycle operations and maintain resource state across the distributed cluster.

    Key Concepts:
        Pool Types: Each pool implementation handles a specific storage backend
                   (filesystem, nfs, etc.) defined by the TYPE class attribute

        Node Access: Pools define which cluster nodes can access their resources
                    through the accessing_nodes property

        Resource Support: Each pool declares supported resource types via the
                         _SUPPORTED_RESOURCES mapping

        Pool Lifecycle: Creation → Attachment → Resource Operations → Detachment → Destruction

    Abstract Methods:
        meet_resource_request(): Determine if pool can satisfy resource requirements

    Configuration Structure:
        Pools use standardized configuration format:
        {
            "meta": {
                "name": "pool_name",
                "uuid": "unique_identifier",
                "type": "pool_type",
                "access": {"nodes": ["node1", "node2"]}
            },
            "spec": {
                # Pool-specific configuration parameters
            }
        }
    """

    # The pool type must be unique in the cluster
    TYPE = None

    # A resource pool may support different types of resources.
    _SUPPORTED_RESOURCES = dict()  # {resource type: resource class object}

    def __init__(self, pool_config):
        self._config = pool_config
        self.meta["uuid"] = uuid.uuid4().hex
        self._resources = dict()  # {resource id: resource object}
        self._connected_nodes = list()

    @property
    def config(self):
        return self._config

    @property
    def meta(self):
        """
        The metadata of the pool's configuration
        """
        return self.config["meta"]

    @property
    def spec(self):
        """
        The specification of the pool's configuration
        """
        return self.config["spec"]

    @property
    def name(self):
        return self.meta["name"]

    @property
    def uuid(self):
        return self.meta["uuid"]

    @property
    def accessing_nodes(self):
        """
        Get the list of accessible node names defined in cluster.json
        """
        return self.meta["access"].get("nodes")

    @accessing_nodes.setter
    def accessing_nodes(self, nodes):
        self.meta["access"]["nodes"] = nodes

    @property
    def type(self):
        return self.meta["type"]

    @property
    def resources(self):
        """
        The resource objects managed by the pool
        """
        return self._resources

    @property
    def connected_nodes(self):
        """
        The worker nodes that are connected to the resource pool
        """
        return self._connected_nodes

    def check_nodes_accessible(self, nodes):
        """
        Check if the resource pool can be accessed from the specified nodes
        """
        node_names = [n.name for n in nodes]
        blocked_nodes = set(node_names).difference(set(self.accessing_nodes))
        if blocked_nodes:
            raise ValueError(
                f"Pool {self.name} cannot be accessed from {blocked_nodes}"
            )

    def customize_pool_config(self, node_name):
        """
        Customized pool configuration, which is passed to the resource backing
        manager, describes the resource pool, the backing manager uses it to
        connect to the physical pool from the worker node.
        """
        return self.config

    def get_info(self):
        """
        Get a copy of the pool's configuration
        """
        return deepcopy(self.config)

    @classmethod
    def define_config(cls, pool_name, pool_params):
        """
        Define the configuration of the pool by its params

        TODO: Decouple this to a converter module, which is responsible
              for converting the cartesian params to python configurations
        """
        config = {
            "meta": {
                "name": pool_name,
                "uuid": None,
                "type": cls.TYPE,
                "access": pool_params.get("access", {}),
            },
            "spec": {},
        }

        return config

    def attach_to(self, node):
        """
        Attach the pool to a specific worker node.
        Then it can be accessed from the node.

        Note the pool's configuration might need to be updated, e.g. for a
        default local filesystem pool, the path is not set yet and must be
        updated after connecting the pool to a worker node.
        """
        r, o = node.proxy.resource.create_pool_connection(
            self.customize_pool_config(node.name)
        )
        if r != 0:
            raise Exception(o["out"])
        self.connected_nodes.append(node)
        return r, o

    def detach_from(self, node):
        """
        Detach the pool from a specific worker node
        Then it cannot be accessed from the node.
        """
        r, o = node.proxy.resource.destroy_pool_connection(self.uuid)
        if r != 0:
            raise Exception(o["out"])
        self.connected_nodes.remove(node)
        return r, o

    @abstractmethod
    def meet_resource_request(self, resource_type, resource_params):
        """
        Check if the pool can meet a resource's request
        """
        # Check if the pool can support a specific resource type
        if not self.get_resource_class(resource_type):
            return False
        return True

    @classmethod
    def get_resource_class(cls, resource_type):
        """
        Get the resource class by the resource type, i.e. these types of the
        resources can be allocated by the pool, e.g. A nfs pool can allocate
        the 'volume' type resources
        """
        return cls._SUPPORTED_RESOURCES.get(resource_type)

    def create_resource_object(self, resource_config):
        """
        Create a resource object without allocation
        """
        meta = resource_config["meta"]

        LOG.debug(f"Create the resource object of {meta['name']} in pool {self.name}")
        res_cls = self.get_resource_class(meta["type"])
        resource = res_cls(resource_config)
        self.resources[resource.uuid] = resource
        return resource.uuid

    def destroy_resource_object(self, resource_id):
        """
        Destroy the resource object.
        The resource object can be destroyed only when the resource is
        released and unbound from all of its backing objects.
        """
        resource = self.resources.get(resource_id)
        LOG.debug(f"Destroy the resource object of {resource.name} in pool {self.name}")
        if resource.allocated:
            raise Exception("Cannot destroy an allocated resource object")
        elif resource.binding_backings:
            raise Exception("Cannot destroy a bound resource object")
        self.resources.pop(resource_id)

    def bind_resource_object(self, resource_id, nodes):
        """
        Bind the resource object to the backing objects on the worker nodes.
        """
        resource = self.resources.get(resource_id)
        return resource.bind_backings(nodes)

    def unbind_resource_object(self, resource_id, nodes=None):
        """
        Unbind the resource object from its backings on the worker nodes.
        Unbind the resource object from all its backings if nodes is not set.
        """
        resource = self.resources.get(resource_id)
        nodes = resource.binding_nodes if not nodes else nodes
        return resource.unbind_backings(nodes)

    def get_resource_binding_nodes(self, resource_id):
        """
        Get the resource binding node tag names for a specified resource.
        """
        resource = self.resources.get(resource_id)
        return [n.tag for n in resource.binding_nodes]

    def clone_resource(self, resource_id, arguments, node=None):
        """
        Clone the resource based on the existing source resource .
        """
        resource = self.resources.get(resource_id)

        LOG.debug(f"Clone a new resource from {resource.name} in pool {self.name}")
        if not node:
            node, _ = resource.get_binding()
        cloned_resource = resource.clone(arguments, node)
        self.resources[cloned_resource.uuid] = cloned_resource
        return cloned_resource.uuid

    def update_resource(self, resource_id, command, arguments, node=None):
        resource = self.resources.get(resource_id)

        LOG.debug(
            f"Update the resource {resource.name} in pool {self.name}: cmd={command}, args={arguments}"
        )
        handler = resource.get_update_handler(command)
        if not handler:
            raise ValueError(
                f"Unsupported command {command} for a {resource.type} resource"
            )
        if not node:
            node, _ = resource.get_binding()

        return handler(arguments, node)

    def get_resource_info(self, resource_id, request=None):
        """
        Get the configuration of a specified resource
        """
        resource = self.resources.get(resource_id)

        LOG.debug(f"Get the resource information of {resource.name}: request={request}")
        config = deepcopy(resource.config)

        # Get a snippet of the configuration
        if request is not None:
            item = ""
            for item in request.split("."):
                if item in config:
                    config = config[item]
                else:
                    raise ValueError(f"Cannot find the requested options {request}")
            else:
                config = {item: config}

        return config
