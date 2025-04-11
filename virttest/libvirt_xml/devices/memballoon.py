"""
memballoon device support class(es)

http://libvirt.org/formatdomain.html#elementsMemBalloon
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Memballoon(base.UntypedDeviceBase):

    __slots__ = (
        "model",
        "autodeflate",
        "stats_period",
        "address",
        "alias_name",
        "driver",
        "freepage_reporting",
    )

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute(
            "model", self, parent_xpath="/", tag_name="memballoon", attribute="model"
        )
        accessors.XMLAttribute(
            "autodeflate",
            self,
            parent_xpath="/",
            tag_name="memballoon",
            attribute="autodeflate",
        )
        accessors.XMLAttribute(
            "stats_period", self, parent_xpath="/", tag_name="stats", attribute="period"
        )
        accessors.XMLElementDict("address", self, parent_xpath="/", tag_name="address")
        accessors.XMLAttribute(
            "alias_name", self, parent_xpath="/", tag_name="alias", attribute="name"
        )
        accessors.XMLElementDict("driver", self, parent_xpath="/", tag_name="driver")
        accessors.XMLAttribute(
            "freepage_reporting",
            self,
            parent_xpath="/",
            tag_name="memballoon",
            attribute="freePageReporting",
        )
        super(Memballoon, self).__init__(
            device_tag="memballoon", virsh_instance=virsh_instance
        )
