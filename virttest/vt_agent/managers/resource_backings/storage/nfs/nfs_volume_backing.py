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
import os

from ..file_volume_backing import _FileVolumeBacking

LOG = logging.getLogger("avocado.service." + __name__)


class _NfsVolumeBacking(_FileVolumeBacking):
    RESOURCE_POOL_TYPE = "nfs"

    def create_object(self, pool_connection):
        if self._uri:
            if not self._uri.startswith(pool_connection.mnt):
                raise ValueError(f"Wrong uri {self._uri} specified in path {pool_connection.mnt}")
        else:
            uri = os.path.join(pool_connection.mnt, self._filename)
            self._uri = os.path.realpath(uri)

        return {
            "spec": {
                "uri": self._uri,
            }
        }
