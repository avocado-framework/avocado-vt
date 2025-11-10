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

from ..backing import ResourceBacking


class VolumeBacking(ResourceBacking):
    RESOURCE_TYPE = "volume"
    RESOURCE_POOL_TYPE = None
    VOLUME_TYPE = None

    def __init__(self, backing_config, pool_connection):
        super().__init__(backing_config, pool_connection)
        self._uri = backing_config["spec"].get("uri")

    @property
    def volume_uri(self):
        return self._uri

    def get_all_resource_info(self, pool_connection):
        config = super().get_all_resource_info(pool_connection)
        config["meta"]["volume-type"] = self.VOLUME_TYPE
        return config
