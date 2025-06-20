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

from virttest import utils_misc

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecPanic(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecPanic, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        panic = dict()
        if self._params.get("enable_pvpanic") == "yes":
            panic_props = dict()
            panic["id"] = utils_misc.generate_random_id()
            arch = self._node.proxy.platform.get_arch()
            if "aarch64" in self._params.get("vm_arch_name", arch):
                panic["type"] = "pvpanic-pci"
            else:
                panic["type"] = "pvpanic"
            if not self._has_device(panic["type"]):
                LOG.warning("%s device is not supported", panic["type"])
                return []
            if panic["type"] == "pvpanic-pci":
                panic["bus"] = self._get_pci_bus(self._params, None, True)
            else:
                ioport = self._params.get("ioport_pvpanic")
                events = self._params.get("events_pvpanic")
                if ioport:
                    panic_props["ioport"] = ioport
                if events:
                    panic_props["events"] = events
            panic["props"] = panic_props
        return panic

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecPanics(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecPanics, self).__init__(name, vt_params, node)
        self._panics = []
        self._parse_params()

    def _define_spec(self):
        self._panics.append(QemuSpecPanic(self._name, self._params, self._node.tag,))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"panics": [panic.spec for panic in self._panics]})
