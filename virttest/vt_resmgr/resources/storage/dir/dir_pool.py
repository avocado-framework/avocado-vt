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

from ...pool import ResourcePool
from ...pool_selector import PoolSelector
from .dir_volume import DirFileVolume

LOG = logging.getLogger("avocado." + __name__)


class DirPool(ResourcePool):
    """
    The local filesystem storage pool
    """

    TYPE = "filesystem"
    _SUPPORTED_RESOURCES = {
        "volume": DirFileVolume,
    }

    @classmethod
    def define_default_config(cls, node_names):
        """
        Define a default filesystem pool if it is not configured by users

        Note the worker node will choose a path, update the pool's path only
        after attaching the pool to a worker node.
        """
        pool_name = f"def_fs_pool_{node_names[0]}"
        pool_params = {
            "type": cls.TYPE,
            "path": "",
            "access": {
                "nodes": node_names,
            },
        }
        return cls.define_config(pool_name, pool_params)

    @classmethod
    def define_config(cls, pool_name, pool_params):
        config = super().define_config(pool_name, pool_params)

        # The path could be "" or a relative path, make up an abspath
        # on the worker node when attaching the pool
        config["spec"]["path"] = pool_params.get("path", "")
        return config

    def attach_to(self, node):
        r, o = super().attach_to(node)

        # The path can be updated only when attaching it to a node
        self.spec["path"] = o["out"]["spec"]["path"]
        return r, o

    def meet_resource_request(self, resource_type, resource_params):
        """
        Check if the dir pool can meet a volume request
        """
        if not super().meet_resource_request(resource_type, resource_params):
            return False

        selectors_string = resource_params.get("volume_pool_selectors")
        if not selectors_string:
            selectors = list()
            storage_type = resource_params.get("storage_type")
            if storage_type:
                selectors.append(
                    {
                        "key": "type",
                        "operator": "==",
                        "values": storage_type,
                    }
                )
            selectors_string = str(selectors)

        return PoolSelector(selectors_string).match(self.config)
