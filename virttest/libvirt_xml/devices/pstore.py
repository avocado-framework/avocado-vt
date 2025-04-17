"""
pstore device support class(es)

https://libvirt.org/formatdomain.html#pstore
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Pstore(base.UntypedDeviceBase):

    __slots__ = ("backend", "path", "size", "size_unit", "address")

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute(
            "backend", self, parent_xpath="/", tag_name="pstore", attribute="backend"
        )
        accessors.XMLElementText("path", self, parent_xpath="/", tag_name="path")
        accessors.XMLElementInt("size", self, parent_xpath="/", tag_name="size")
        accessors.XMLAttribute(
            property_name="size_unit",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="size",
            attribute="unit",
        )
        accessors.XMLElementDict("address", self, parent_xpath="/", tag_name="address")
        super(Pstore, self).__init__(device_tag="pstore", virsh_instance=virsh_instance)
