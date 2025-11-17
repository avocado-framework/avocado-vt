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


class NfsFileVolume(FileVolume):
    """
    The nfs file-based volume resource
    """

    def bind_backings(self, nodes):
        """
        Bind the nfs resource to its backings on the worker nodes.
        Note: A nfs volume resource can have many bindings
        """
        for node in nodes:
            _, backing_id = self.get_binding(node)
            if backing_id:
                LOG.debug(
                    f"The nfs volume has already bound to a backing on {node.name}"
                )
                continue

            r, o = node.proxy.resource.create_resource_backing(
                self.get_backing_config(node.name)
            )
            if r != 0:
                raise Exception(o["out"])

            self._update_binding(node, o["out"]["backing"])
            self._update_uri(node.name, o["out"]["spec"]["uri"])

    def unbind_backings(self, nodes):
        """
        Unbind the nfs volume from its backings on the worker nodes
        """
        for node in nodes:
            _, backing_id = self.get_binding(node)
            if not backing_id:
                LOG.debug(
                    f"The nfs volume has already unbound from the backing on {node.name}"
                )
                continue

            r, o = node.proxy.resource.destroy_resource_backing(backing_id)
            if r != 0:
                raise Exception(o["out"])

            self._update_binding(node, None)
            self._update_uri(node.name, None)
