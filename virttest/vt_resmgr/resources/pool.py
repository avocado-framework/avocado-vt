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

from virttest.vt_cluster import cluster


class _ResourcePool(ABC):
    """
    A resource pool is used to manage resources. A resource must be
    allocated from a specific pool, and a pool can hold many resources
    """

    _POOL_TYPE = None
    _SUPPORTED_RESOURCE_CLASSES = dict()  # resource type: resource class

    def __init__(self, pool_config):
        self._config = pool_config
        self.pool_meta["uuid"] = uuid.uuid4().hex
        self._resources = dict()  # {resource id: resource object}

        # The pool can be accessed by all worker nodes by default
        if not self.accessing_nodes:
            self.accessing_nodes = [n.name for n in cluster.get_all_nodes()]

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
    def accessing_nodes(self):
        """
        Get the list of accessible node names defined in cluster.json
        """
        return self.pool_meta["access"].get("nodes")

    @accessing_nodes.setter
    def accessing_nodes(self, nodes):
        self.pool_meta["access"]["nodes"] = nodes

    @classmethod
    def get_pool_type(cls):
        return cls._POOL_TYPE

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

    def get_info(self):
        return deepcopy(self.pool_config)

    @classmethod
    def define_config(cls, pool_name, pool_params):
        return {
            "meta": {
                "name": pool_name,
                "uuid": None,
                "type": pool_params["type"],
                "access": pool_params.get("access", {}),
            },
            "spec": {},
        }

    def attach(self, node):
        """
        Attach itself to a specific worker node
        """
        r, o = node.proxy.resource.connect_pool(
            self.pool_id, self.customize_pool_config(node.name)
        )
        if r != 0:
            raise Exception(o["out"])
        return r, o

    def detach(self, node):
        """
        Detach itself from a specific worker node
        """
        r, o = node.proxy.resource.disconnect_pool(self.pool_id)
        if r != 0:
            raise Exception(o["out"])
        return r, o

    @abstractmethod
    def meet_conditions(self, condition_params):
        """
        Check if the pool can meet the conditions
        """
        raise NotImplementedError

    def define_resource_config(self, resource_name, resource_type, resource_params):
        """
        Define the resource configuration by the cartesian params:
          {"meta": {...}, "spec": {...}}
        It depends on the specific type of resource.
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
    def get_resource_class(cls, resource_type):
        """
        Get the resource class by the resource type, i.e. these types of the
        resources can be allocated by the pool, e.g. A nfs pool can allocate
        the 'volume' type resources
        """
        return cls._SUPPORTED_RESOURCE_CLASSES.get(resource_type)

    def create_object(self):
        pass

    def destroy_object(self):
        pass

    def create_resource_object_by(self, source_resource, node_names):
        new_obj = source_resource.create_object_by_self(self.pool_id, node_names)
        self.resources[new_obj.resource_id] = new_obj
        return new_obj.resource_id

    def create_resource_object(self, resource_config):
        """
        Create a resource object without allocation
        """
        meta = resource_config["meta"]
        res_cls = self.get_resource_class(meta["type"])
        res_obj = res_cls(resource_config)
        res_obj.create_object()
        self.resources[res_obj.resource_id] = res_obj
        return res_obj.resource_id

    def destroy_resource_object(self, resource_id):
        """
        Destroy the resource object, all its backings should be released
        """
        res_obj = self.resources[resource_id]
        res_obj.destroy_object()
        self.resources.pop(resource_id)

    def clone_resource(self, resource_id, arguments):
        resource = self.resources.get(resource_id)
        cloned_resource = resource.clone(arguments)
        self.resources[cloned_resource.resource_id] = cloned_resource
        return cloned_resource.resource_id

    def update_resource(self, resource_id, config):
        resource = self.resources.get(resource_id)
        cmd, arguments = config.popitem()

        # "nodes" should be the tags defined in the param "nodes"
        node_tags = arguments.pop("nodes", list())
        if node_tags:
            # Check if the node can access the resource pool
            node_names = [cluster.get_node_by_tag(t).name for t in node_tags]
            if not set(node_names).issubset(set(self.accessing_nodes)):
                raise ValueError(
                    f"Not all nodes({node_names}) can access the pool {self.pool_id}"
                )
            # Update the arguments with node names
            arguments["nodes"] = node_names

        handler = resource.get_update_handler(cmd)
        return handler(arguments)

    def get_resource_info(self, resource_id, verbose=False, sync=False):
        """
        Get the configuration of a specified resource
        """
        resource = self.resources.get(resource_id)
        if sync:
            resource.sync()

        config = deepcopy(resource.resource_config)
        if verbose:
            config["meta"]["pool"] = deepcopy(self.pool_config)

        return config
