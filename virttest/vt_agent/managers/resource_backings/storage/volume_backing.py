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

from ..backing import _ResourceBacking

LOG = logging.getLogger("avocado.service." + __name__)


class _VolumeBacking(_ResourceBacking):
    RESOURCE_TYPE = "volume"
    RESOURCE_POOL_TYPE = None

    def __init__(self, backing_config):
        super().__init__(backing_config)
        self._uri = backing_config["spec"].get("uri")
