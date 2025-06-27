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
# Copyright: Red Hat Inc. 2025 and Avocado contributors
# Authors: Yongxue Hong <yhong@redhat.com>


from virttest.qemu_devices.utils import set_cmdline_format_by_cfg
from virttest.qemu_devices import qdevices


def create_iommu_device(iommu, parent_bus, format_cfg):
    dev = qdevices.QDevice(iommu["type"], iommu.get("props"),
                           parent_bus=parent_bus)
    if iommu == "intel-iommu":
        set_cmdline_format_by_cfg(
            dev, format_cfg, "intel_iommu"
        )
    if iommu == "virtio-iommu-pci":
        set_cmdline_format_by_cfg(
            dev, format_cfg, "virtio_iommu"
        )

    return dev
