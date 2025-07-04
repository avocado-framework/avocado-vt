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

import ast
import uuid
from abc import ABC, abstractmethod
from copy import deepcopy

from virttest.vt_cluster import cluster


class _Resource(ABC):
    """
    A resource defines what users request, it's independent of a VM,
    users can request kinds of resources for any purpose. The resource
    can be bound to several backings on different worker nodes.

    Note: A resource can bind to only one backing on a worker node.
    """

    _RESOURCE_TYPE = None

    def __init__(self, resource_config):
        self._config = resource_config
        self.resource_meta["uuid"] = uuid.uuid4().hex
        self._handlers = {
            "bind": self.bind,
            "unbind": self.unbind,
            "allocate": self.allocate,
            "release": self.release,
            "sync": self.sync,
        }

    @property
    def resource_config(self):
        return self._config

    @property
    def resource_spec(self):
        return self.resource_config["spec"]

    @property
    def resource_meta(self):
        return self.resource_config["meta"]

    @property
    def resource_id(self):
        return self.resource_meta["uuid"]

    @property
    def resource_type(self):
        return self.resource_meta["type"]

    @property
    def resource_pool(self):
        return self.resource_meta["pool"]

    @resource_pool.setter
    def resource_pool(self, pool_id):
        self.resource_meta["pool"] = pool_id

    @property
    def resource_bindings(self):
        return self.resource_meta["bindings"]

    @property
    def resource_binding_nodes(self):
        return [d["node"] for d in self.resource_bindings]

    @property
    def resource_binding_backings(self):
        return [d["backing"] for d in self.resource_bindings if d["backing"]]

    @property
    def resource_allocated(self):
        return self.resource_meta["allocated"]

    def _set_backing(self, node_name, backing_id):
        for binding in self.resource_bindings:
            if binding["node"] == node_name:
                binding["backing"] = backing_id
                break

    def _get_backing(self, node_name):
        """
        Get the backing id on the specified worker node
        """
        backing = None
        for binding in self.resource_bindings:
            if binding["node"] == node_name:
                backing = binding["backing"]
        return backing

    @classmethod
    def _get_binding_nodes(cls, pool_selectors):
        """
        Get the worker node names where the resource is bound to.
        The nodes can be set by access.nodes in the xxx_pool_selectors params,
          volume_pool_selectors_image1 = [
            {"key": "access.nodes", "operator": "contains", values": "node1 node2"},
          ]
        When it's not set, use all partition nodes.

        :param pool_selectors: List of selectors defined by xxx_pool_selectors,
                               e.g. volume_pool_selectors
        :type pool_selectors: list
        :return: The worker node names
        :rtype: list
        """
        nodes = list()
        for d in pool_selectors:
            if "access.nodes" == d["key"]:
                nodes = [cluster.get_node_by_tag(t).name for t in d["values"].split()]
                break
        return [n.name for n in cluster.partition.nodes] if not nodes else nodes

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        selectors = ast.literal_eval(
            resource_params.get("volume_pool_selectors", list())
        )
        nodes = cls._get_binding_nodes(selectors)

        return {
            "meta": {
                "uuid": None,
                "name": resource_name,
                "type": cls._RESOURCE_TYPE,
                "pool": None,
                "allocated": False,
                "bindings": [{"node": n, "backing": None} for n in nodes],
            },
            "spec": {},
        }

    @classmethod
    def define_config(cls, resource_name, resource_params):
        # Define the configuration based on the previous cartesian params
        return cls._define_config_legacy(resource_name, resource_params)

    def get_update_handler(self, command):
        return self._handlers.get(command)

    def create_object_by_self(self, pool_id, access_nodes):
        config = deepcopy(self.resource_config)
        config["meta"].update(
            {
                "pool": pool_id,
                "bindings": [{"node": n, "backing": None} for n in access_nodes],
                "allocated": False,
            }
        )

        return self.__class__(config)

    def create_object(self):
        pass

    def destroy_object(self):
        if self.resource_allocated:
            raise Exception("Cannot destroy it for it's not released yet")
        elif self.resource_binding_backings:
            raise Exception("Cannot destroy it for it's bound")

    @abstractmethod
    def clone(self, arguments):
        """
        Clone the resource, return a new resource object
        """
        raise NotImplementedError

    @abstractmethod
    def bind(self, arguments):
        """
        Bind the resource to one or more worker nodes
        """
        raise NotImplementedError

    @abstractmethod
    def unbind(self, arguments):
        """
        Unbind the resource to one or more worker nodes
        """
        raise NotImplementedError

    @abstractmethod
    def allocate(self, arguments):
        """
        Allocate the resource
        """
        raise NotImplementedError

    @abstractmethod
    def release(self, arguments):
        """
        Release the resource
        """
        raise NotImplementedError

    @abstractmethod
    def sync(self, arguments):
        """
        Sync the resource configuration
        """
        raise NotImplementedError
