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

from .volume import Volume

LOG = logging.getLogger("avocado." + __name__)


class FileVolume(Volume):
    """File based volume resource"""

    VOLUME_TYPE = "file"

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
            # It fails when the image file doesn't come from the selected pool
            filename = os.path.basename(image_name)
            # When image_name is set to an abspath, i.e. all worker nodes
            # should access it with the same abspath
            uri = {"*": image_name}
        else:
            image_format = resource_params.get("image_format", "qcow2")
            filename = f"{image_name}.{image_format}"
            uri = dict()

        config["spec"].update(
            {
                "filename": filename,
                "uri": uri,
            },
        )

        return config

    def get_backing_config(self, node_name):
        return {
            "meta": {
                "uuid": self.uuid,
                "type": self.type,
                "pool": self.pool,
            },
            "spec": {
                "uri": self._get_uri(node_name),
                "filename": self.spec["filename"],
            },
        }

    def define_config_by_self(self):
        postfix = utils_misc.generate_random_string(8)
        config = super().define_config_by_self()
        config["spec"].update(
            {
                "allocation": None,
                "filename": f"{self.spec['filename']}_{postfix}",
                "uri": dict(),
            }
        )
        return config

    def resize(self, arguments, node):
        """
        Resize the file based volume
        """
        size = arguments.get("size") if arguments else None
        if size is None:
            raise ValueError(f"New volume size is not set")

        bsize = int(normalize_data_size(size, "B"))
        if bsize != self.spec["size"]:
            node, backing_id = self.get_binding(node)
            r, o = node.proxy.resource.update_resource_by_backing(
                backing_id,
                "resize",
                arguments,
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

    def allocate(self, arguments, node):
        # Pass size as an argument to its backing, because size can change
        arguments = arguments if arguments else dict()
        arguments["size"] = self.spec["size"]
        node, backing_id = self.get_binding(node)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id,
            "allocate",
            arguments,
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.meta.update(
            {
                "allocated": config["meta"]["allocated"],
            }
        )
        self.spec.update(
            {
                "allocation": config["spec"]["allocation"],
            }
        )

    def release(self, arguments, node):
        node, backing_id = self.get_binding(node)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id,
            "release",
            arguments,
        )
        if r != 0:
            raise Exception(o["out"])

        self.meta.update(
            {
                "allocated": False,
            }
        )
        self.spec.update(
            {
                "allocation": None,
            }
        )

    def clone(self, arguments, node):
        # Reset options of the cloned resource
        postfix = utils_misc.generate_random_string(8)
        confs = copy.deepcopy(self.config)
        confs["spec"].update(
            {
                "filename": f"{self.spec['filename']}_clone_{postfix}",
                "uri": dict(),
                "allocation": None,
            }
        )
        confs["meta"].update(
            {
                "name": f"{self.name}_clone_{postfix}",
                "allocated": False,
            }
        )

        # Create the cloned resource object and bind it to the backings
        # on the same worker nodes as the source resource
        cloned_obj = self.__class__(confs)
        cloned_obj.bind_backings(self.binding_nodes)

        # Clone the new resource by the source
        node, backing_id = cloned_obj.get_binding(node)
        _, source_backing_id = self.get_binding(node)
        arguments = arguments if arguments else dict()
        arguments["source"] = source_backing_id
        r, o = node.proxy.resource.clone_resource_by_backing(backing_id, arguments)
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        cloned_obj.meta.update(
            {
                "allocated": config["meta"]["allocated"],
            }
        )
        cloned_obj.spec.update(
            {
                "allocation": config["spec"]["allocation"],
            }
        )

        return cloned_obj

    def sync(self, arguments, node):
        node, backing_id = self.get_binding(node)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id,
            "sync",
            arguments,
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.meta.update(
            {
                "allocated": config["meta"]["allocated"],
            }
        )
        self.spec.update(
            {
                "allocation": config["spec"]["allocation"],
            }
        )
