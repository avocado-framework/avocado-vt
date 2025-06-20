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
# Authors: Yongxue Hong <yhong@redhat.com>


import logging

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecDebug(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecDebug, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        debug = dict()
        debug_props = dict()
        debug_backend = dict()

        if self._params.get("enable_debugcon") == "yes":
            debug["type"] = "isa-debugcon"

        if self._params.get("anaconda_log", "no") == "yes":
            debug["type"] = "anaconda_log"
            debug["bus"] = self._get_pci_bus(self.params, None, True)

        debug_props["backend"] = debug_backend
        debug["props"] = debug_props
        return debug

    def _parse_params(self):
        self._spec.update({"debug": self._define_spec()})
