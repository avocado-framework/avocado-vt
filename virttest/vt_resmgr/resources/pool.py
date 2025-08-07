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


class _ResourcePool(ABC):
    """
    A resource pool is used to manage resources. A resource must be allocated
    from a specific pool, and a resource pool can hold many resources.
    """

    # The pool type must be uniq in the cluster
    TYPE = None

    # A resource pool may support different types of resources.
    _SUPPORTED_RESOURCES = dict()  # {resource type: resource class object}

    def __init__(self, pool_config):
        self._config = pool_config
        self.meta["uuid"] = uuid.uuid4().hex
        self._resources = dict()  # {resource id: resource object}

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

    def check_nodes_accessible(self, nodes):
        """
        Check if the resource pool can be accessed from the specified nodes
        """
        node_names = [n.name for n in nodes]
        blocked_nodes = set(node_names).difference(set(self.accessing_nodes))
        if blocked_nodes:
            raise ValueError(f"Pool {self.name} cannot be accessed from {blocked_nodes}")

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

    def attach(self, node):
        """
        Attach the pool to a specific worker node.
        Then it can be accessed from the node.

        Note the pool's configuration might need to be updated, e.g. for a
        default local filesystem pool, the path is not set yet and must be
        updated after connecting the pool to a worker node.
        """
        r, o = node.proxy.resource.connect_pool(
            self.uuid, self.customize_pool_config(node.name)
        )
        if r != 0:
            raise Exception(o["out"])
        return r, o

    def detach(self, node):
        """
        Detach the pool from a specific worker node
        Then it cannot be accessed from the node.
        """
        r, o = node.proxy.resource.disconnect_pool(self.uuid)
        if r != 0:
            raise Exception(o["out"])
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

    def define_resource_config(self, resource_name, resource_type, resource_params):
        """
        Define the resource configuration by the cartesian params, it depends
        on the specific type of resource.
        """
        LOG.info(f"Define the resource configuration of {resource_name} by pool {self.name}")

        res_cls = self.get_resource_class(resource_type)
        config = res_cls.define_config(resource_name, resource_params)
        config["meta"].update(
            {
                "pool": self.uuid,
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
        return cls._SUPPORTED_RESOURCES.get(resource_type)

    def create_object(self):
        pass

    def destroy_object(self):
        pass

    def create_resource_object_by(self, source_resource):
        LOG.info(f"Create a resource object based on resource {source_resource.name} in pool {self.name}")
        if not self.get_resource_class(source_resource.type):
            raise ValueError(
                f"The target pool {self.name} doesn't support a "
                f"{source_resource.type} type resource"
            )

        new_resource = source_resource.create_object_by_self()
        new_resource.pool = self.uuid
        self.resources[new_resource.uuid] = new_resource
        return new_resource.uuid

    def create_resource_object(self, resource_config):
        """
        Create a resource object without allocation
        """
        meta = resource_config["meta"]

        LOG.info(f"Create the resource object of {meta['name']} in pool {self.name}")
        res_cls = self.get_resource_class(meta["type"])
        resource = res_cls(resource_config)
        resource.create_object()
        self.resources[resource.uuid] = resource
        return resource.uuid

    def destroy_resource_object(self, resource_id):
        """
        Destroy the resource object, all its backings should be released
        """
        resource = self.resources.pop(resource_id)

        LOG.info(f"Destroy the resource object of {resource.name} in pool {self.name}")
        resource.destroy_object()

    def bind_resource_object(self, resource_id, nodes):
        """
        Bind the resource object to the backing objects on the worker nodes.
        """
        self.check_nodes_accessible(nodes)
        resource = self.resources.get(resource_id)
        return resource.bind_backings(nodes)

    def unbind_resource_object(self, resource_id, nodes=None):
        """
        Unbind the resource object from its backing objects on the worker nodes.
        Unbind the resource object from all its backings if nodes is not set.
        """
        resource = self.resources.get(resource_id)
        if nodes:
            self.check_nodes_accessible(nodes)
        else:
            nodes = resource.binding_nodes
        return resource.unbind_backings(nodes)

    def clone_resource(self, resource_id, arguments, nodes):
        """
        Clone the resource based on the existing source resource .
        """
        resource = self.resources.get(resource_id)

        LOG.info(f"Clone a new resource from {resource.name} in pool {self.name}")
        if nodes:
            self.check_nodes_accessible(nodes)
        cloned_resource = resource.clone(arguments, nodes)
        self.resources[cloned_resource.uuid] = cloned_resource
        return cloned_resource.uuid

    def update_resource(self, resource_id, command, arguments, nodes):
        resource = self.resources.get(resource_id)

        LOG.info(
            f"Update the resource {resource.name} in pool {self.name}: cmd={command}, args={arguments}"
        )
        if nodes:
            self.check_nodes_accessible(nodes)

        handler = resource.get_update_handler(command)
        if not handler:
            raise ValueError(f"Unsupported command {command} for a {resource.type} resource")

        return handler(arguments, nodes)

    def get_resource_info(self, resource_id, request=None):
        """
        Get the configuration of a specified resource
        """
        resource = self.resources.get(resource_id)

        LOG.info(f"Get the resource information of {resource.name}: request={request}")
        config = deepcopy(resource.config)

        # Get a snippet of the configuration
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
