"""
Address device / device descriptor class

http://libvirt.org/formatdomain.html#elementsAddress
"""

from virttest.libvirt_xml import accessors, xcepts
from virttest.libvirt_xml.devices import base


class Address(base.TypedDeviceBase):

    __slots__ = ("attrs",)

    def __init__(self, type_name, virsh_instance=base.base.virsh):
        # Blindly accept any/all attributes as simple dictionary
        accessors.XMLElementDict("attrs", self, parent_xpath="/", tag_name="address")
        accessors.XMLElementNest(
            "zpci_attrs",
            self,
            parent_xpath="/",
            tag_name="zpci",
            subclass=self.Zpci,
            subclass_dargs={"virsh_instance": virsh_instance},
        )
        super(self.__class__, self).__init__(
            device_tag="address", type_name=type_name, virsh_instance=virsh_instance
        )

    @classmethod
    def new_from_dict(cls, attributes, virsh_instance=base.base.virsh):
        # type_name is mandatory, throw exception if doesn't exist
        try:
            # pop() so don't process again in loop below
            instance = cls(
                type_name=attributes.pop("type_name"), virsh_instance=virsh_instance
            )
        except (KeyError, AttributeError):
            raise xcepts.LibvirtXMLError("type_name is manditory for " "Address class")
        # Stick property values in as attributes
        xtfroot = instance.xmltreefile.getroot()
        for key, value in list(attributes.items()):
            xtfroot.set(key, value)
        return instance

    @classmethod
    def new_from_element(cls, element, virsh_instance=base.base.virsh):
        # element uses type attribute, class uses type_name
        edict = dict(list(element.items()))
        try:
            edict["type_name"] = edict.pop("type")
        except (KeyError, AttributeError):
            raise xcepts.LibvirtXMLError(
                "type attribute is manditory for " "Address class"
            )
        return cls.new_from_dict(edict, virsh_instance=virsh_instance)

    class Zpci(base.base.LibvirtXMLBase):
        """Represents the optional subelement for zpci addresses"""

        __slots__ = ("uid", "fid")

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLAttribute(
                "uid",
                self,
                parent_xpath="/",
                tag_name="zpci",
                attribute="uid",
            )
            accessors.XMLAttribute(
                "fid",
                self,
                parent_xpath="/",
                tag_name="zpci",
                attribute="fid",
            )
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<zpci/>"

        @classmethod
        def new_from_dict(cls, attributes, virsh_instance=base.base.virsh):
            instance = cls(virsh_instance=virsh_instance)
            instance.uid = attributes["uid"]
            instance.fid = attributes["fid"]
            return instance
