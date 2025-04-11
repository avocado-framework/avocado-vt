"""
input device support class(es)

http://libvirt.org/formatdomain.html#elementsInput
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base, librarian


class Input(base.TypedDeviceBase):
    __slots__ = (
        "input_bus",
        "input_type",
        "model",
        "address",
        "source_evdev",
        "driver",
        "alias",
    )

    def __init__(self, type_name, virsh_instance=base.base.virsh):
        super(Input, self).__init__(
            device_tag="input", type_name=type_name, virsh_instance=virsh_instance
        )
        accessors.XMLAttribute(
            property_name="input_bus",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="input",
            attribute="bus",
        )
        accessors.XMLAttribute(
            property_name="input_type",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="input",
            attribute="type",
        )
        accessors.XMLAttribute(
            property_name="model",
            libvirtxml=self,
            parent_xpath="/",
            tag_name="input",
            attribute="model",
        )
        accessors.XMLElementNest(
            "address",
            self,
            parent_xpath="/",
            tag_name="address",
            subclass=self.Address,
            subclass_dargs={"type_name": "usb", "virsh_instance": virsh_instance},
        )
        accessors.XMLAttribute(
            "source_evdev", self, parent_xpath="/", tag_name="source", attribute="evdev"
        )
        accessors.XMLElementDict("driver", self, parent_xpath="/", tag_name="driver")
        accessors.XMLElementDict("alias", self, parent_xpath="/", tag_name="alias")

    # For convenience
    Address = librarian.get("address")

    # For convenience
    Address = librarian.get("address")

    def new_input_address(self, type_name="usb", **dargs):
        """
        Return a new input Address instance and set properties from dargs
        """
        new_one = self.Address(type_name=type_name, virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one
