"""
interface device support class(es)

http://libvirt.org/formatdomain.html#elementsNICS
http://libvirt.org/formatnwfilter.html#nwfconceptsvars
"""

from virttest.libvirt_xml import accessors, xcepts
from virttest.libvirt_xml.devices import base, librarian


class Interface(base.TypedDeviceBase):

    __slots__ = (
        "source",
        "hostdev_address",
        "managed",
        "mac_address",
        "bandwidth",
        "model",
        "coalesce",
        "link_state",
        "target",
        "driver",
        "address",
        "boot",
        "rom",
        "mtu",
        "filterref",
        "backend",
        "virtualport",
        "alias",
        "ips",
        "teaming",
        "vlan",
        "port",
        "acpi",
        "portForwards",
        "trustGuestRxFilters",
        "source_local",
        "tune",
    )

    def __init__(self, type_name="network", virsh_instance=base.base.virsh):
        super(Interface, self).__init__(
            device_tag="interface", type_name=type_name, virsh_instance=virsh_instance
        )
        accessors.XMLElementDict(
            property_name="source",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="source",
        )
        accessors.XMLElementNest(
            "hostdev_address",
            self,
            parent_xpath="/source",
            tag_name="address",
            subclass=self.Address,
            subclass_dargs={"type_name": "pci", "virsh_instance": virsh_instance},
        )
        accessors.XMLElementDict(
            property_name="source_local",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/source",
            tag_name="local",
        )
        accessors.XMLAttribute(
            property_name="managed",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="interface",
            attribute="managed",
        )
        accessors.XMLAttribute(
            property_name="trustGuestRxFilters",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="interface",
            attribute="trustGuestRxFilters",
        )
        accessors.XMLElementDict(
            property_name="target",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="target",
        )
        accessors.XMLElementDict(
            property_name="backend",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="backend",
        )
        accessors.XMLAttribute(
            property_name="mac_address",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="mac",
            attribute="address",
        )
        accessors.XMLAttribute(
            property_name="link_state",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="link",
            attribute="state",
        )
        accessors.XMLAttribute(
            property_name="boot",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="boot",
            attribute="order",
        )
        accessors.XMLElementNest(
            "bandwidth",
            self,
            parent_xpath="/",
            tag_name="bandwidth",
            subclass=self.Bandwidth,
            subclass_dargs={"virsh_instance": virsh_instance},
        )
        accessors.XMLElementNest(
            "driver",
            self,
            parent_xpath="/",
            tag_name="driver",
            subclass=self.Driver,
            subclass_dargs={"virsh_instance": virsh_instance},
        )
        accessors.XMLElementNest(
            "filterref",
            self,
            parent_xpath="/",
            tag_name="filterref",
            subclass=self.Filterref,
            subclass_dargs={"virsh_instance": virsh_instance},
        )
        accessors.XMLAttribute(
            property_name="model",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="model",
            attribute="type",
        )
        accessors.XMLElementDict(
            property_name="coalesce",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/coalesce/rx",
            tag_name="frames",
        )
        accessors.XMLElementDict(
            property_name="rom",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="rom",
        )
        accessors.XMLElementDict(
            property_name="mtu",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="mtu",
        )
        accessors.XMLElementNest(
            "address",
            self,
            parent_xpath="/",
            tag_name="address",
            subclass=self.Address,
            subclass_dargs={"type_name": "pci", "virsh_instance": virsh_instance},
        )
        accessors.XMLElementDict("alias", self, parent_xpath="/", tag_name="alias")
        accessors.XMLElementDict(
            property_name="acpi",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="acpi",
        )
        accessors.XMLElementList(
            property_name="ips",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            marshal_from=self.marshal_from_ips,
            marshal_to=self.marshal_to_ips,
        )
        accessors.XMLElementDict(
            property_name="teaming",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="teaming",
        )
        accessors.XMLElementNest(
            "vlan",
            self,
            parent_xpath="/",
            tag_name="vlan",
            subclass=self.Vlan,
            subclass_dargs={"virsh_instance": virsh_instance},
        )
        accessors.XMLElementNest(
            "virtualport",
            self,
            parent_xpath="/",
            tag_name="virtualport",
            subclass=self.VirtualPort,
            subclass_dargs={"virsh_instance": virsh_instance},
        )
        accessors.XMLElementDict(
            property_name="port",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="port",
        )
        accessors.XMLElementList(
            property_name="portForwards",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            marshal_from=self.marshal_from_portForwards,
            marshal_to=self.marshal_to_portForwards,
            has_subclass=True,
        )
        accessors.XMLElementNest(
            "tune",
            self,
            parent_xpath="/",
            tag_name="tune",
            subclass=self.Tune,
            subclass_dargs={"virsh_instance": virsh_instance},
        )

    # For convenience
    Address = librarian.get("address")

    Filterref = librarian.get("filterref")

    @staticmethod
    def marshal_from_ips(item, index, libvirtxml):
        """Convert an Address instance into tag + attributes"""
        """Convert a dictionary into a tag + attributes"""
        del index  # not used
        del libvirtxml  # not used
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError(
                "Expected a dictionary of ip" "attributes, not a %s" % str(item)
            )
        return ("ip", dict(item))  # return copy of dict, not reference

    @staticmethod
    def marshal_to_ips(tag, attr_dict, index, libvirtxml):
        """Convert a tag + attributes into an Address instance"""
        del index  # not used
        del libvirtxml  # not used
        if not tag == "ip":
            return None  # skip this one
        return dict(attr_dict)  # return copy of dict, not reference

    @staticmethod
    def marshal_from_portForwards(item, index, libvirtxml):
        """
        Convert an PortForward object to portForward tag and xml element.
        """
        if isinstance(item, Interface.PortForward):
            return "portForward", item
        elif isinstance(item, dict):
            portForward = Interface.PortForward()
            portForward.setup_attrs(**item)
            return "portForward", portForward
        else:
            raise xcepts.LibvirtXMLError(
                "Expected a list of PortForward " "instances, not a %s" % str(item)
            )

    @staticmethod
    def marshal_to_portForwards(tag, new_treefile, index, libvirtxml):
        """
        Convert a portForward tag xml element to an object of PortForward.
        """
        if tag != "portForward":
            return None  # Don't convert this item
        newone = Interface.PortForward(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone

    def new_bandwidth(self, **dargs):
        """
        Return a new interface bandwidth instance from dargs
        """
        new_one = self.Bandwidth(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_driver(self, **dargs):
        """
        Return a new interface driver instance from dargs
        """
        new_one = self.Driver(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_iface_address(self, **dargs):
        """
        Return a new interface Address instance and set properties from dargs
        """
        new_one = self.Address("pci", virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_filterref(self, **dargs):
        """
        Return a new interface filterref instance from dargs
        """
        new_one = self.Filterref(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_vlan(self, **dargs):
        """
        This defines a new element vlan in the interface xml.

        :param dargs: a dict with keys as "trunk" and "tags",
        like {'trunk': 'yes', 'tags': [{'id': '42'}, {'id': '123', 'nativeMode': 'untagged'}]}
        :Return: a new vlan instance from dargs
        """
        new_one = self.Vlan(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    class Bandwidth(base.base.LibvirtXMLBase):
        """
        Interface bandwidth xml class.

        Properties:

        inbound:
            dict. Keys: average, peak, floor, burst
        outbound:
            dict. Keys: average, peak, floor, burst
        """

        __slots__ = ("inbound", "outbound")

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementDict(
                "inbound", self, parent_xpath="/", tag_name="inbound"
            )
            accessors.XMLElementDict(
                "outbound", self, parent_xpath="/", tag_name="outbound"
            )
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<bandwidth/>"

    class Driver(base.base.LibvirtXMLBase):
        """
        Interface Driver xml class.

        Properties:

        driver:
            dict.
        host:
            dict. Keys: csum, gso, tso4, tso6, ecn, ufo
        guest:
            dict. Keys: csum, gso, tso4, tso6, ecn, ufo
        """

        __slots__ = ("driver_attr", "driver_host", "driver_guest")

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementDict(
                "driver_attr", self, parent_xpath="/", tag_name="driver"
            )
            accessors.XMLElementDict(
                "driver_host", self, parent_xpath="/", tag_name="host"
            )
            accessors.XMLElementDict(
                "driver_guest", self, parent_xpath="/", tag_name="guest"
            )
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<driver/>"

    class Vlan(base.base.LibvirtXMLBase):
        """
        Interface vlan xml class.

        Properties:

        trunk:
            attribute.
        tags:
            list. tags element dict list
        """

        __slots__ = ("trunk", "tags")

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLAttribute(
                property_name="trunk",
                libvirtxml=self,
                forbidden=None,
                parent_xpath="/",
                tag_name="vlan",
                attribute="trunk",
            )
            accessors.XMLElementList(
                property_name="tags",
                libvirtxml=self,
                parent_xpath="/",
                marshal_from=self.marshal_from_tag,
                marshal_to=self.marshal_to_tag,
            )
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<vlan/>"

        @staticmethod
        def marshal_from_tag(item, index, libvirtxml):
            """Convert a dictionary into a tag + attributes"""
            del index  # not used
            del libvirtxml  # not used
            if not isinstance(item, dict):
                raise xcepts.LibvirtXMLError(
                    "Expected a dictionary of tag " "attributes, not a %s" % str(item)
                )
                # return copy of dict, not reference
            return ("tag", dict(item))

        @staticmethod
        def marshal_to_tag(tag, attr_dict, index, libvirtxml):
            """Convert a tag + attributes into a dictionary"""
            del index  # not used
            del libvirtxml  # not used
            if tag != "tag":
                return None  # skip this one
            return dict(attr_dict)  # return copy of dict, not reference@

    class VirtualPort(base.base.LibvirtXMLBase):
        """
        Interface virtualport xml class.

        Properties:

        type:
            attribute.
        parameters:
            dict.
        """

        __slots__ = ("type", "parameters")

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLAttribute(
                property_name="type",
                libvirtxml=self,
                forbidden=None,
                parent_xpath="/",
                tag_name="virtualport",
                attribute="type",
            )
            accessors.XMLElementDict(
                "parameters", self, parent_xpath="/", tag_name="parameters"
            )
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<virtualport/>"

    class PortForward(base.base.LibvirtXMLBase):
        """
        Interface portForward xml class.

        Properties:

        attrs:
            dict.
        ranges:
            list.
        """

        __slots__ = ("attrs", "ranges")

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementDict(
                property_name="attrs",
                libvirtxml=self,
                forbidden=None,
                parent_xpath="/",
                tag_name="portForward",
            )
            accessors.XMLElementList(
                property_name="ranges",
                libvirtxml=self,
                forbidden=None,
                parent_xpath="/",
                marshal_from=self.marshal_from_ranges,
                marshal_to=self.marshal_to_ranges,
            )
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<portForward/>"

        @staticmethod
        def marshal_from_ranges(item, index, libvirtxml):
            if not isinstance(item, dict):
                raise xcepts.LibvirtXMLError(
                    "Expected a dictionary of range" "attributes, not a %s" % str(item)
                )
            return ("range", dict(item))

        @staticmethod
        def marshal_to_ranges(tag, attr_dict, index, libvirtxml):
            if not tag == "range":
                return None
            return dict(attr_dict)

    class Tune(base.base.LibvirtXMLBase):
        """
        Interface tune xml class.

        Properties:

        sndbuf:
            int
        """

        __slots__ = ("sndbuf",)

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementInt(
                property_name="sndbuf",
                libvirtxml=self,
                forbidden=None,
                parent_xpath="/",
                tag_name="sndbuf",
            )
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<tune/>"
