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

import os

from ..file_volume_backing import FileVolumeBacking


class NfsVolumeBacking(FileVolumeBacking):
    RESOURCE_POOL_TYPE = "nfs"

    def __init__(self, backing_config, pool_connection):
        super().__init__(backing_config, pool_connection)

        if self._uri:
            if not self._uri.startswith(pool_connection.mnt):
                raise ValueError(f"Cannot find {self._uri} in {pool_connection.mnt}")
        else:
            uri = os.path.join(pool_connection.mnt, self._filename)
            self._uri = os.path.realpath(uri)
