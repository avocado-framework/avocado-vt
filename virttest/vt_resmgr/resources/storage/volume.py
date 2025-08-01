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

from ..resource import _Resource


class _Volume(_Resource):
    """
    Storage volumes are abstractions of physical partitions,
    LVM logical volumes, file-based disk images
    """

    TYPE = "volume"
    _VOLUME_TYPE = None

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        size = normalize_data_size(
            resource_params.get("image_size", "20G"), order_magnitude="B"
        )

        config = super()._define_config_legacy(resource_name, resource_params)
        config["meta"].update(
            {
                "volume-type": cls._VOLUME_TYPE,
            }
        )
        config["spec"].update(
            {
                "size": size,
                "allocation": None,
                "uri": None,
            }
        )

        return config
