"""
Libvirt virtio related utilities.

:copyright: 2022 Red Hat Inc.
"""

import logging

from virttest.libvirt_xml import vm_xml
from virttest.libvirt_xml.devices import iommu
from virttest.utils_libvirt import libvirt_vmxml
from virttest.utils_test import libvirt

LOG = logging.getLogger("avocado." + __name__)


def create_iommu(iommu_dict):
    """
    Create iommu device

    :param iommu_dict: Attrs of iommu
    :return: Iommu device object
    """
    iommu_dev = iommu.Iommu()
    iommu_dev.setup_attrs(**iommu_dict)
    LOG.debug("iommu XML: %s", iommu_dev)
    return iommu_dev


def add_iommu_dev(vm, iommu_dict):
    """
    Add iommu device to the vm

    :param vm: vm object
    :param iommu_dict: Attrs of iommu device
    """
    libvirt_vmxml.remove_vm_devices_by_type(vm, "iommu")
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm.name)
    features = vmxml.features
    if not features.has_feature("ioapic") and iommu_dict.get("model") == "intel":
        features.add_feature("ioapic", "driver", "qemu")
        vmxml.features = features

    iommu_dev = create_iommu(iommu_dict)
    libvirt.add_vm_device(vmxml, iommu_dev)
