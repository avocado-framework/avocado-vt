"""
Generic character device support for serial, parallel, channel, and console

http://libvirt.org/formatdomain.html#elementCharSerial
"""

from virttest.libvirt_xml import accessors, base, xcepts
from virttest.libvirt_xml.devices import base
from virttest.libvirt_xml.devices.seclabel import Seclabel


class CharacterBase(base.TypedDeviceBase):

    __slots__ = ("sources", "targets")

    # Not overriding __init__ because ABC cannot hide device_tag as expected

    # Accessors just wrap private helpers in UntypedDeviceBase class

    def get_targets(self):
        """
        Return a list of dictionaries containing each target's attributes.
        """
        return self._get_list("target")

    def set_targets(self, value):
        """
        Set all sources to the value list of dictionaries of target attributes.
        """
        self._set_list("target", value)

    def del_targets(self):
        """
        Remove the list of dictionaries containing each target's attributes.
        """
        self._del_list("target")

    # Some convenience methods so appending to sources/targets is easier
    def add_source(self, **attributes):
        """
        Convenience method for appending a source from dictionary of attributes
        """
        sources = self.sources
        new_source = self.Source()
        new_source.setup_attrs(attrs=attributes)
        sources.append(new_source)
        self.sources = sources

    def add_target(self, **attributes):
        """
        Convenience method for appending a target from dictionary of attributes
        """
        self._add_item("targets", **attributes)

    def update_source(self, index, **attributes):
        """
        Convenience method for merging values into a source's attributes
        """
        self._update_item("sources", index, **attributes)

    def update_target(self, index, **attributes):
        """
        Convenience method for merging values into a target's attributes
        """
        self._update_item("targets", index, **attributes)

    @staticmethod
    def marshal_from_sources(item, index, libvirtxml):
        """
        Convert an xml object to source tag and xml element.
        """
        if isinstance(item, CharacterBase.Source):
            return "source", item
        elif isinstance(item, dict):
            source = CharacterBase.Source()
            source.setup_attrs(**item)
            return "source", source
        else:
            raise xcepts.LibvirtXMLError(
                "Expected a list of Source " "instances, not a %s" % str(item)
            )

    @staticmethod
    def marshal_to_sources(tag, new_treefile, index, libvirtxml):
        """
        Convert a source tag xml element to an object of Source.
        """
        if tag != "source":
            return None
        newone = CharacterBase.Source(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone

    class Source(base.base.LibvirtXMLBase):

        __slots__ = ("attrs", "seclabels")

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementDict("attrs", self, parent_xpath="/", tag_name="source")
            accessors.XMLElementList(
                "seclabels",
                self,
                parent_xpath="/",
                marshal_from=self.marshal_from_seclabels,
                marshal_to=self.marshal_to_seclabels,
                has_subclass=True,
            )
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<source/>"

        @staticmethod
        def marshal_from_seclabels(item, index, libvirtxml):
            """
            Convert an xml object to seclabel tag and xml element.
            """
            if isinstance(item, Seclabel):
                return "seclabel", item
            elif isinstance(item, dict):
                seclabel = Seclabel()
                seclabel.setup_attrs(**item)
                return "seclabel", seclabel
            else:
                raise xcepts.LibvirtXMLError(
                    "Expected a list of Seclabel " "instances, not a %s" % str(item)
                )

        @staticmethod
        def marshal_to_seclabels(tag, new_treefile, index, libvirtxml):
            """
            Convert a seclabel tag xml element to an object of Seclabel.
            """
            if tag != "seclabel":
                return None
            newone = Seclabel(virsh_instance=libvirtxml.virsh)
            newone.xmltreefile = new_treefile
            return newone
