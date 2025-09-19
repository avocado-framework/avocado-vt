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


class ResourceBacking(ABC):
    # The type of the resource binding to itself
    RESOURCE_TYPE = None

    # The type of the pool where the resource is allocated
    RESOURCE_POOL_TYPE = None

    def __init__(self, custom_resource_config, pool_connection=None):
        """
        Never add a changeable attribute, e.g. allocated, because a resource
        can have more than one backing, when it changes from one backing, we
        have to update all other backings' allocated attribute. So allocated
        can only be an item of spec or an attribute for the resource object.
        """
        self._uuid = uuid.uuid4().hex
        self._resource_uuid = custom_resource_config["meta"]["uuid"]
        self._resource_pool_uuid = custom_resource_config["meta"]["pool"]

        self._handlers = {
            "allocate": self.allocate_resource,
            "release": self.release_resource,
            "sync": self.sync_resource_info,
        }

    @property
    def uuid(self):
        return self._uuid

    @property
    def resource_uuid(self):
        return self._resource_uuid

    @property
    def resource_pool_uuid(self):
        return self._resource_pool_uuid

    def get_update_handler(self, cmd):
        return self._handlers[cmd]

    @abstractmethod
    def is_resource_allocated(self, pool_connection=None):
        raise NotImplementedError

    @abstractmethod
    def allocate_resource(self, pool_connection, arguments=None):
        raise NotImplementedError

    @abstractmethod
    def release_resource(self, pool_connection, arguments=None):
        raise NotImplementedError

    @abstractmethod
    def clone_resource(self, pool_connection, source_backing, arguments=None):
        raise NotImplementedError

    @abstractmethod
    def sync_resource_info(self, pool_connection, arguments=None):
        raise NotImplementedError
