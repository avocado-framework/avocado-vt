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

from avocado.utils import process

# pylint: disable=E0611
from avocado_vt.agent.core.logger import DEFAULT_LOG_NAME

from .volume_backing import VolumeBacking

LOG = logging.getLogger(f"{DEFAULT_LOG_NAME}." + __name__)


class FileVolumeBacking(VolumeBacking):
    VOLUME_TYPE = "file"

    def __init__(self, backing_config, pool_connection):
        super().__init__(backing_config, pool_connection)
        if self._uri:
            self._uri = os.path.realpath(self._uri)
        self._filename = backing_config["spec"]["filename"]
        self._handlers.update(
            {
                "resize": self.resize_volume,
            }
        )

    def is_resource_allocated(self, pool_connection=None):
        if self.volume_uri:
            return os.path.exists(self.volume_uri)
        return False

    def allocate_resource(self, pool_connection, arguments=None):
        if not self.is_resource_allocated():
            dir_name = os.path.dirname(self._uri)
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)

            size = arguments["size"]
            cmd = f"fallocate -x -l {size} {self._uri}"
            try:
                process.run(
                    cmd,
                    shell=True,
                    verbose=False,
                    ignore_status=False,
                )
            except Exception:
                self.release_resource(pool_connection)
                raise
        else:
            LOG.debug("The volume has already been allocated")
        return self.sync_resource_info(pool_connection)

    def release_resource(self, pool_connection, arguments=None):
        if self.is_resource_allocated():
            if os.path.exists(self._uri):
                os.unlink(self._uri)
        else:
            LOG.debug("The volume has already been released.")

    def resize_volume(self, pool_connection, arguments):
        pass

    def sync_resource_info(self, pool_connection, arguments=None):
        allocation, allocated = None, self.is_resource_allocated()
        if allocated:
            s = os.stat(self.volume_uri)
            allocation = s.st_size

        return {
            "meta": {
                "allocated": allocated,
            },
            "spec": {
                "uri": self.volume_uri,
                "allocation": allocation,
            },
        }

    def clone_resource(self, pool_connection, source_backing, arguments=None):
        if not source_backing.is_resource_allocated():
            raise RuntimeError("Cannot clone a resource which is not allocated yet")

        # TODO: Clone the resource by other ways
        def_clone_cmd = f"cp -rp {source_backing._uri} {self._uri}"
        process.run(
            def_clone_cmd,
            shell=True,
            verbose=False,
            ignore_status=False,
        )

        return self.sync_resource_info(pool_connection)
