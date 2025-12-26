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

import uuid
from abc import ABC, abstractmethod
from copy import deepcopy


class Resource(ABC):
    """
    Abstract base class for resources in the VT resource management system.

    A resource represents a logical asset (volume, network port, etc.) that can be
    requested and allocated by tests. Resources are VM-independent and provide a unified
    abstraction for various types of test assets across the distributed cluster environment.

    Resources operate through a distributed backing system where each resource can have
    multiple backing objects on different worker nodes, but only one backing per node.
    This enables multi-node access to shared resources while maintaining node-local
    implementations for performance and isolation.

    Key Concepts:
        Resource Types: Each resource implementation handles a specific asset type
                       (volume, port, etc.) defined by the TYPE class attribute

        Multi-Node Binding: Resources can be bound to multiple backings on worker nodes
                            simultaneously, the backings provide node-local access

        Backing Constraint: Each resource maintains exactly one backing per worker node
                           to prevent conflicts and ensure consistent state

        Command System: Resources support lifecycle commands (allocate, release, sync, etc.)
                       executed through their backing objects

    Resource Lifecycle:
        1. Creation: Resource object created without allocation
        2. Binding: Resource bound to its backings on worker node
        3. Allocation: Physical resource allocated on target nodes
        4. Operations: Resource commands executed (sync, resize, etc.)
        5. Release: Physical resource released but binding maintained
        6. Unbinding: Resource unbound from worker nodes
        7. Destruction: Resource object removed

    Abstract Methods:
        bind_backings(): Create backing objects on specified worker nodes
        unbind_backings(): Remove backing objects from worker nodes
        clone(): Create allocated copy of resource on specified node
        allocate(): Allocate physical resource on specified node
        release(): Release physical resource on specified node
        sync(): Synchronize resource state from worker node

    Binding Architecture:
        Resources maintain a list of bindings where each binding represents:
        - node: Worker node object where backing exists
        - backing: UUID of the backing object on that node

    Command Handling:
        Resources use a handler-based system for lifecycle operations:
        - Command handlers registered in _handlers dictionary
        - Commands executed on specific worker nodes through backings
        - Standard commands: allocate, release, sync (resource-type specific commands possible)

    Configuration Structure:
        Resources use standardized configuration format:
        {
            "meta": {
                "uuid": "resource_identifier",
                "name": "resource_name",
                "type": "resource_type",
                "pool": "parent_pool_uuid",
                "allocated": false
            },
            "spec": {
                # Resource-specific parameters
            }
        }
    """

    # The resource type must be unique in the cluster
    TYPE = None

    def __init__(self, resource_config):
        self._config = resource_config
        self.meta["uuid"] = uuid.uuid4().hex
        self._bindings = list()  # [{"node": node object, "backing": backing uuid},]
        self._handlers = {
            "allocate": self.allocate,
            "release": self.release,
            "sync": self.sync,
        }

    @property
    def config(self):
        return self._config

    @property
    def spec(self):
        return self.config["spec"]

    @property
    def meta(self):
        return self.config["meta"]

    @property
    def uuid(self):
        return self.meta["uuid"]

    @property
    def name(self):
        return self.meta["name"]

    @property
    def type(self):
        return self.meta["type"]

    @property
    def pool(self):
        return self.meta["pool"]

    @pool.setter
    def pool(self, pool_id):
        self.meta["pool"] = pool_id

    @property
    def bindings(self):
        return self._bindings

    @property
    def binding_nodes(self):
        return [d["node"] for d in self.bindings]

    @property
    def binding_backings(self):
        return [d["backing"] for d in self.bindings if d["backing"]]

    @property
    def allocated(self):
        return self.meta["allocated"]

    def get_backing_config(self, node_name):
        """
        The required resource configuration for a specific backing object.
        Used as an argument to create its backing object.
        """
        return self.config

    def _update_binding(self, node, backing_id=None):
        for idx in range(0, len(self.bindings)):
            binding = self.bindings[idx]
            if binding["node"].name == node.name:
                if backing_id:
                    binding["backing"] = backing_id
                else:
                    self.bindings.pop(idx)
                break
        else:
            if backing_id:
                self.bindings.append({"node": node, "backing": backing_id})
            else:
                raise ValueError(f"Cannot delete the binding on node {node.name}")

    def get_binding(self, node=None):
        """
        Get the binding on the specified worker node, if node is not set,
        return the first binding
        """
        if not node:
            n, b = self.bindings[0]["node"], self.bindings[0]["backing"]
        else:
            for binding in self.bindings:
                if binding["node"].name == node.name:
                    n, b = node, binding["backing"]
                    break
            else:
                n, b = node, None
        return n, b

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        """
        Define the resource configuration by the current cartesian params, in
        future new params will be designed for a specific type of resource.
        """
        return {
            "meta": {
                "uuid": None,
                "name": resource_name,
                "type": cls.TYPE,
                "pool": None,
                "allocated": False,
            },
            "spec": {},
        }

    @classmethod
    def define_config(cls, resource_name, resource_params):
        """
        TODO: Decouple it to a converter module, which is responsible
              for converting the cartesian params to python configurations
        """
        return cls._define_config_legacy(resource_name, resource_params)

    def get_update_handler(self, command):
        return self._handlers.get(command)

    def define_config_by_self(self):
        """
        Define the resource configuration by itself.

        Depends on a specific type of resource, *ALWAYS* reset its required
        metadata and specifications for the new resource object.
        Note: Cannot define a new object directly by itself because the new
              resource could be a different resource object. e.g. Create a
              _NfsFileVolume from a _DirFileVolume
        """
        config = deepcopy(self.config)
        config["meta"].update(
            {
                "uuid": uuid.uuid4().hex,
                "pool": None,
                "allocated": False,
            }
        )
        return config

    @abstractmethod
    def bind_backings(self, nodes):
        """
        Bind the resource to the backings on the specified worker nodes.
        """
        raise NotImplementedError

    @abstractmethod
    def unbind_backings(self, nodes):
        """
        Unbind the resource from the backings on the specified worker nodes.
        """
        raise NotImplementedError

    @abstractmethod
    def clone(self, arguments, node):
        """
        Clone the resource on a specified worker node.
        """
        raise NotImplementedError

    @abstractmethod
    def allocate(self, arguments, node):
        """
        Allocate the resource on a specified worker node.
        """
        raise NotImplementedError

    @abstractmethod
    def release(self, arguments, node):
        """
        Release the resource on a specified worker node.
        """
        raise NotImplementedError

    @abstractmethod
    def sync(self, arguments, node):
        """
        Sync up the resource configuration on a specified worker node.
        """
        raise NotImplementedError
