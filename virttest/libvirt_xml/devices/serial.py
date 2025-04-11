"""
Classes to support XML for serial devices

http://libvirt.org/formatdomain.html#elementCharSerial
"""

from virttest.libvirt_xml import accessors, base
from virttest.libvirt_xml.devices.character import CharacterBase


class Serial(CharacterBase):

    __slots__ = (
        "protocol_type",
        "log_file",
        "target_port",
        "target_type",
        "target_model",
        "sources",
        "alias",
        "address",
    )

    def __init__(self, type_name="pty", virsh_instance=base.virsh):
        # Additional attribute for protocol type (raw, telnet, telnets, tls)
        accessors.XMLAttribute(
            "protocol_type",
            self,
            parent_xpath="/",
            tag_name="protocol",
            attribute="type",
        )
        accessors.XMLAttribute(
            "log_file", self, parent_xpath="/", tag_name="log", attribute="file"
        )
        accessors.XMLAttribute(
            "target_port", self, parent_xpath="/", tag_name="target", attribute="port"
        )
        accessors.XMLAttribute(
            "target_type", self, parent_xpath="/", tag_name="target", attribute="type"
        )
        accessors.XMLAttribute(
            "target_model",
            self,
            parent_xpath="/target",
            tag_name="model",
            attribute="name",
        )
        accessors.XMLElementList(
            "sources",
            self,
            parent_xpath="/",
            marshal_from=self.marshal_from_sources,
            marshal_to=self.marshal_to_sources,
            has_subclass=True,
        )
        accessors.XMLElementDict("alias", self, parent_xpath="/", tag_name="alias")
        accessors.XMLElementDict("address", self, parent_xpath="/", tag_name="address")
        super(Serial, self).__init__(
            device_tag="serial", type_name=type_name, virsh_instance=virsh_instance
        )
