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

from ..file_volume import _FileVolume

LOG = logging.getLogger("avocado." + __name__)


class _DirFileVolume(_FileVolume):
    """
    The local filesystem file-based volume resource
    """

    @property
    def backing_config(self):
        return {
            "meta": {
                "uuid": self.uuid,
                "type": self.type,
                "pool": self.pool,
            },
            "spec": {
                "uri": self.spec["uri"],
                "filename": self.spec["filename"],
                "size": self.spec["size"],
            }
        }

    def bind_backings(self, nodes):
        # Note a local dir resource has one and only one binding.
        if self.binding_backings:
            raise RuntimeError(f"Cannot bind a bound dir volume {self.name}")

        r, o = nodes[0].proxy.resource.create_backing_object(self.backing_config)
        if r != 0:
            raise Exception(o["out"])

        backing_uuid = o["out"]
        self._add_binding(nodes[0], backing_uuid)

    def unbind_backings(self, nodes):
        if not self.binding_backings:
            raise RuntimeError(f"Cannot unbind an unbound dir volume {self.name}")

        node, backing_id = self._get_binding(nodes[0])
        r, o = node.proxy.resource.destroy_backing_object(backing_id)
        if r != 0:
            raise Exception(o["out"])

        self._del_binding(node, backing_id)
