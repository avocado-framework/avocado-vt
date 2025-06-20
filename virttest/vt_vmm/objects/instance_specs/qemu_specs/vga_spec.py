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


class QemuSpecVGA(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecVGA, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        vga = dict()

        if self._params.get("vga"):
            _vga = self._params.get("vga")
            fallback = self._params.get("vga_use_legacy_expression") == "yes"
            machine_type = self._params.get("machine_type", "")
            pcie = machine_type.startswith("q35") or machine_type.startswith(
                "arm64-pci"
            )
            vga["bus"] = self._get_bus(self._params, "vga", pcie)
            vga_dev_map = {
                "std": "VGA",
                "cirrus": "cirrus-vga",
                "vmware": "vmware-svga",
                "qxl": "qxl-vga",
                "virtio": "virtio-vga",
            }
            vga_dev = vga_dev_map.get(_vga, None)
            if machine_type.startswith("arm64-pci:"):
                if _vga == "virtio" and not self._has_device(vga_dev):
                    # Arm doesn't usually supports 'virtio-vga'
                    vga_dev = "virtio-gpu-pci"
            elif machine_type.startswith("s390-ccw-virtio"):
                if _vga == "virtio":
                    vga_dev = "virtio-gpu-ccw"
                else:
                    vga_dev = None
            elif "-mmio:" in machine_type:
                if _vga == "virtio":
                    vga_dev = "virtio-gpu-device"
                else:
                    vga_dev = None
            if vga_dev is None:
                fallback = True
                vga["bus"] = None
            # fallback if qemu not has such a device
            elif not self._has_device(vga_dev):
                fallback = True
            if fallback:
                vga_dev = "VGA-%s" % _vga
            vga["type"] = vga_dev

        return vga

    def _parse_params(self):
        self._spec.update({"vga": self._define_spec()})
