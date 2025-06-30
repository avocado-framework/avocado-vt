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
from .nfs_volume import NfsFileVolume

LOG = logging.getLogger("avocado." + __name__)


class NfsPool(ResourcePool):
    TYPE = "nfs"
    _SUPPORTED_RESOURCES = {
        "volume": NfsFileVolume,
    }

    @classmethod
    def define_config(cls, pool_name, pool_params):
        config = super().define_config(pool_name, pool_params)
        config["spec"].update(
            {
                "server": pool_params["server"],
                "export": pool_params["export"],
                "mount-options": pool_params.get("mount_options", dict()),
                "mount": pool_params.get("mount_point", dict()),
            }
        )
        return config

    @property
    def mnt(self):
        """
        Mount points can be different across the worker nodes.
        {"*": "/mnt/dir"} means all worker nodes have the same mount point.
        """
        return self.spec["mount"]

    @property
    def mnt_opts(self):
        """
        Mount options can be different across the worker nodes.
        {"*": "rw"} means all worker nodes have the same mount options.
        """
        return self.spec["mount-options"]

    def _get_mnt_opts(self, node_name):
        for n, opts in self.mnt_opts.items():
            if n == "*" or n == node_name:
                return opts
        return None

    def _get_mnt(self, node_name):
        for n, m in self.mnt.items():
            if n == "*" or n == node_name:
                return m
        return None

    def _update_mnt(self, node_name, mount_point):
        mp = self.mnt.get("*")
        if not mp:
            self.mnt[node_name] = mount_point

    def attach_to(self, node):
        r, o = super().attach_to(node)
        if r == 0:
            # Don't care about the mount options
            self._update_mnt(node.name, o["out"]["spec"]["mount"])
        return r, o

    def customize_pool_config(self, node_name):
        return {
            "meta": {
                "uuid": self.uuid,
                "type": self.type,
            },
            "spec": {
                "server": self.spec["server"],
                "export": self.spec["export"],
                "mount-options": self._get_mnt_opts(node_name),
                "mount": self._get_mnt(node_name),
            },
        }

    def meet_resource_request(self, resource_type, resource_params):
        """
        Check if the nfs pool can meet the resource's requirements
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
