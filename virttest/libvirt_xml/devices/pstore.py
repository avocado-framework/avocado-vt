"""
pstore device support class(es)

https://libvirt.org/formatdomain.html#pstore
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base, librarian


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
        accessors.XMLElementNest(
            "address",
            self,
            parent_xpath="/",
            tag_name="address",
            subclass=self.Address,
            subclass_dargs={"type_name": "pci", "virsh_instance": virsh_instance},
        )
        super(Pstore, self).__init__(device_tag="pstore", virsh_instance=virsh_instance)

    # For convenience
    Address = librarian.get("address")

    def new_pstore_address(self, type_name="pci", **dargs):
        """
        Return a new pstore Address instance and set properties from dargs
        """
        new_one = self.Address(type_name=type_name, virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one
