"""
Support for the iommu device XML

http://libvirt.org/formatdomain.html#elementsDevices
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Iommu(base.UntypedDeviceBase):

    __slots__ = ("model", "driver", "alias", "address")

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute(
            property_name="model",
            libvirtxml=self,
            parent_xpath="/",
            tag_name="iommu",
            attribute="model",
        )
        accessors.XMLElementDict(
            property_name="driver", libvirtxml=self, parent_xpath="/", tag_name="driver"
        )
        accessors.XMLElementDict("alias", self, parent_xpath="/", tag_name="alias")
        accessors.XMLElementDict("address", self, parent_xpath="/", tag_name="address")
        super(Iommu, self).__init__(device_tag="iommu", virsh_instance=virsh_instance)
