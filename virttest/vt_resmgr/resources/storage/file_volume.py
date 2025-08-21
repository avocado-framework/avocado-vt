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

import copy
import logging
import os

from virttest import utils_misc
from virttest.utils_numeric import normalize_data_size

from .volume import _Volume

LOG = logging.getLogger("avocado." + __name__)


class _FileVolume(_Volume):
    """File based volume resource"""

    _VOLUME_TYPE = "file"

    def __init__(self, resource_config):
        super().__init__(resource_config)
        self._handlers.update(
            {
                "resize": self.resize,
            }
        )

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        config = super()._define_config_legacy(resource_name, resource_params)

        image_name = resource_params.get("image_name", "image")
        if os.path.isabs(image_name):
            # FIXME: the image file may not come from this pool
            filename = os.path.basename(image_name)
            uri = image_name
        else:
            image_format = resource_params.get("image_format", "qcow2")
            filename = f"{image_name}.{image_format}"
            uri = None

        config["spec"].update(
            {
                "filename": filename,
                "uri": uri,
            }
        )

        return config

    def create_object_by_self(self):
        postfix = utils_misc.generate_random_string(8)
        volume_obj = super().create_object_by_self()
        volume_obj.spec.update(
            {
                "allocation": None,
                "filename": f"{self.spec['filename']}_{postfix}",
                "uri": None,
            }
        )
        return volume_obj

    def resize(self, arguments, node=None):
        """
        Resize the file based volume
        """
        size = arguments.get("size") if arguments else None
        if size is None:
            raise ValueError(f"New volume size is not set")

        bsize = int(normalize_data_size(size, "B"))
        if bsize != self.spec["size"]:
            node, backing_id = self._get_binding(node)
            r, o = node.proxy.resource.update_resource_by_backing(
                backing_id, "resize", arguments,
            )
            if r != 0:
                raise Exception(o["out"])

            config = o["out"]
            self.spec.update(
                {
                    "size": bsize,
                    "allocation": config["spec"]["allocation"],
                }
            )
        else:
            LOG.warning("The new volume size is the same as the old.")

    def allocate(self, arguments, node=None):
        node, backing_id = self._get_binding(node)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, "allocate", arguments,
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.meta["allocated"] = config["meta"]["allocated"]
        self.spec.update(
            {
                "uri": config["spec"]["uri"],
                "allocation": config["spec"]["allocation"],
            }
        )

    def release(self, arguments, node=None):
        node, backing_id = self._get_binding(node)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, "release", arguments,
        )
        if r != 0:
            raise Exception(o["out"])

        self.meta["allocated"] = False
        self.spec.update(
            {
                "uri": None,
                "allocation": None,
            }
        )

    def clone(self, arguments, node=None):
        node, backing_id = self._get_binding(node)
        r, o = node.proxy.resource.clone_resource_by_backing(
            backing_id, arguments
        )
        if r != 0:
            raise Exception(o["out"])
        config = o["out"]

        # Reset options of the cloned resource
        postfix = utils_misc.generate_random_string(8)
        confs = copy.deepcopy(self.config)
        confs["spec"].update(
            {
                "filename": config["spec"]["filename"],
                "uri": config["spec"]["uri"],
                "allocation": config["spec"]["allocation"],
            }
        )
        confs["meta"].update(
            {
                "name": f"{self.name}_clone_{postfix}",
                "allocated": config['meta']['allocated'],
            }
        )
        cloned_obj = self.__class__(confs)
        cloned_obj.create_object()
        cloned_obj.bind_backings(self.binding_nodes)
        return cloned_obj

    def sync(self, arguments, node=None):
        LOG.debug(f"Sync up the configuration of volume {self.uuid}")
        node, backing_id = self._get_binding(node)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, "sync", arguments,
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.meta["allocated"] = config["meta"]["allocated"]
        self.spec.update(
            {
                "uri": config["spec"]["uri"],
                "allocation": config["spec"]["allocation"],
            }
        )
