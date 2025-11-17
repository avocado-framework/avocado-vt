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

from ..file_volume import FileVolume

LOG = logging.getLogger("avocado." + __name__)


class DirFileVolume(FileVolume):
    """
    The local filesystem file-based volume resource
    """

    def bind_backings(self, nodes):
        # Note a local dir resource has one and only one binding.
        if self.binding_backings:
            raise RuntimeError(f"Cannot bind a bound dir volume {self.name}")

        node = nodes[0]
        r, o = node.proxy.resource.create_resource_backing(
            self.get_backing_config(node.name)
        )
        if r != 0:
            raise Exception(o["out"])

        self._update_binding(node, o["out"]["backing"])
        self._update_uri(node.name, o["out"]["spec"]["uri"])

    def unbind_backings(self, nodes):
        if not self.binding_backings:
            raise RuntimeError(f"Cannot unbind an unbound dir volume {self.name}")

        node, backing_id = self.get_binding(nodes[0])
        r, o = node.proxy.resource.destroy_resource_backing(backing_id)
        if r != 0:
            raise Exception(o["out"])

        self._update_binding(node, None)
        self._update_uri(node.name, None)
