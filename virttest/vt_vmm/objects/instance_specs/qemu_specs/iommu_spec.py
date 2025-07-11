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


class QemuSpecIOMMU(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecIOMMU, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        iommu = dict()
        iommu_props = dict()

        if self._params.get("intel_iommu") and self._has_device("intel-iommu"):
            iommu["type"] = "intel-iommu"
            iommu_props["intremap"] = self._params.get("iommu_intremap", "on")
            iommu_props["device_iotlb"] = self._params.get("iommu_device_iotlb", "on")
            iommu_props["caching_mode"] = self._params.get("iommu_caching_mode")
            iommu_props["eim"] = self._params.get("iommu_eim")
            iommu_props["x_buggy_eim"] = self._params.get("iommu_x_buggy_eim")
            iommu_props["version"] = self._params.get("iommu_version")
            iommu_props["x_scalable_mode"] = self._params.get("iommu_x_scalable_mode")
            iommu_props["dma_drain"] = self._params.get("iommu_dma_drain")
            iommu_props["pt"] = self._params.get("iommu_pt")
            iommu_props["aw_bits"] = self._params.get("iommu_aw_bits")
            iommu["props"] = iommu_props

        elif self._params.get("virtio_iommu") and self._has_device(
                "virtio-iommu-pci"):
            iommu["type"] = "virtio-iommu-pci"
            iommu["bus"] = "pci.0"
            iommu_props["pcie_direct_plug"] = "yes"
            virtio_iommu_extra_params = self._params.get("virtio_iommu_extra_params")
            if virtio_iommu_extra_params:
                for extra_param in virtio_iommu_extra_params.strip(",").split(","):
                    key, value = extra_param.split("=")
                    iommu_props[key] = value
            iommu["props"] = iommu_props

        return iommu

    def _parse_params(self):
        self._spec.update({"iommu": self._define_spec()})
