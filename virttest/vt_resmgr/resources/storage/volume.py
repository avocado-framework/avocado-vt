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

from virttest.utils_numeric import normalize_data_size

from ..resource import Resource


class Volume(Resource):
    """
    Storage volumes are abstractions of physical partitions,
    LVM logical volumes, file-based disk images
    """

    TYPE = "volume"
    VOLUME_TYPE = None

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        size = normalize_data_size(
            resource_params.get("image_size", "20G"), order_magnitude="B"
        )

        config = super()._define_config_legacy(resource_name, resource_params)
        config["meta"].update(
            {
                "volume-type": cls.VOLUME_TYPE,
            }
        )
        config["spec"].update(
            {
                "size": size,
                "allocation": None,
                "uri": dict(),  # uri can differ across worker nodes
            }
        )

        return config

    def _get_uri(self, node_name):
        for n, u in self.spec["uri"].items():
            if node_name == "*" or node_name == n:
                return u
        return None

    def _update_uri(self, node_name, uri=None):
        # Never update the user specified uri, e.g. image_name=/abspath/f
        volume_uri = self.spec["uri"].get("*")
        if not volume_uri:
            if uri:
                self.spec["uri"][node_name] = uri
            else:
                self.spec["uri"].pop(node_name)
