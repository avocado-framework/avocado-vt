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


class QemuSpecInput(QemuSpec):
    def __init__(self, name, vt_params, node, input):
        super(QemuSpecInput, self).__init__(name, vt_params, node)
        self._input = input
        self._parse_params()

    def _define_spec(self):
        input_device = self._input
        input_params = self._params.object_params(input_device)
        input = dict()
        input["id"] = input_device

        dev_map = {
            "mouse": {"virtio": "virtio-mouse"},
            "keyboard": {"virtio": "virtio-keyboard"},
            "tablet": {"virtio": "virtio-tablet"},
        }
        input_type = dev_map.get(input_params["input_dev_type"])
        bus_type = input_params["input_dev_bus_type"]

        machine_type = input_params.get("machine_type", "")
        bus = "PCI"
        if machine_type.startswith("q35") or machine_type.startswith("arm64"):
            bus = "PCIE"

        if bus_type == "virtio":
            if "-mmio:" in machine_type:
                bus = "virtio-bus"
            elif machine_type.startswith("s390"):
                bus = "virtio-bus"

        input["type"] = input_type
        input["bus"] = bus
        return input

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecInputs(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecInputs, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for input in self._params.objects("inputs"):
            self._specs.append(QemuSpecInput(self._name, self._params,
                                             self._node.tag, input))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"inputs": [input.spec for input in self._specs]})
