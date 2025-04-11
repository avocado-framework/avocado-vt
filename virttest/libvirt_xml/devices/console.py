"""
Console device support class(es)

http://libvirt.org/formatdomain.html#elementCharSerial
"""

from virttest.libvirt_xml import accessors, base
from virttest.libvirt_xml.devices.character import CharacterBase


class Console(CharacterBase):

    __slots__ = (
        "protocol_type",
        "target_port",
        "target_type",
        "sources",
        "alias",
        "log",
    )

    def __init__(self, type_name="pty", virsh_instance=base.virsh):
        accessors.XMLAttribute(
            "protocol_type",
            self,
            parent_xpath="/",
            tag_name="protocol",
            attribute="type",
        )
        accessors.XMLAttribute(
            "target_port", self, parent_xpath="/", tag_name="target", attribute="port"
        )
        accessors.XMLAttribute(
            "target_type", self, parent_xpath="/", tag_name="target", attribute="type"
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
        accessors.XMLElementDict("log", self, parent_xpath="/", tag_name="log")
        super(Console, self).__init__(
            device_tag="console", type_name=type_name, virsh_instance=virsh_instance
        )
