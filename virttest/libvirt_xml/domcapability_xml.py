"""
Module simplifying manipulation of XML described at
http://libvirt.org/formatdomaincaps.html
"""

from virttest import xml_utils
from virttest.libvirt_xml import base, accessors, xcepts


class DomCapabilityXML(base.LibvirtXMLBase):

    """
    Handler of libvirt domcapabilities operations.

    Properties:
        features:
            DomCapFeaturesXML instance to deal with domain features
    """
    __slots__ = ('features', 'max')
    __schema_name__ = 'domcapabilities'

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementNest(property_name='features',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='features',
                                 subclass=DomCapFeaturesXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLAttribute('max', self, parent_xpath='/',
                               tag_name='vcpu', attribute='max')
        super(DomCapabilityXML, self).__init__(virsh_instance)
        self['xml'] = self.__dict_get__('virsh').domcapabilities().stdout.strip()


class DomCapFeaturesXML(base.LibvirtXMLBase):
    """
    Handler of feature element in libvirt domcapabilities.

    Properties:
        gic_supported:
            string in "yes" or "no"
        gic_enums:
            list of enum dict in /gic
    """
    __slots__ = ('gic_supported', 'gic_enums')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLAttribute(property_name='gic_supported',
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='gic',
                               attribute='supported')
        accessors.AllForbidden(property_name='gic_enums',
                               libvirtxml=self)
        super(DomCapFeaturesXML, self).__init__(virsh_instance)

    def get_gic_enums(self):
        """
        Return EnumXML instance list of gic
        """
        enum_list = []
        for enum_node in self.xmltreefile.findall('/gic/enum'):
            xml_str = xml_utils.ElementTree.tostring(enum_node)
            new_enum = EnumXML()
            new_enum.xml = xml_str
            enum_list.append(new_enum)
        return enum_list


class ValueXML(base.LibvirtXMLBase):
    """
    Value elements of EnumXML
    """

    __slots__ = ('value',)

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementText(property_name='value',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='value')
        super(ValueXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<value/>'


class EnumXML(base.LibvirtXMLBase):
    """
    Handler of Enum element in libvirt domcapabilities

    Properties:
        name:
            string of name for enum
        values:
            list of ValueXML instance
    """
    __slots__ = ('name', 'values')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLAttribute(property_name='name',
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='enum',
                               attribute='name')
        accessors.XMLElementList(property_name='values',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 marshal_from=self.marshal_from_values,
                                 marshal_to=self.marshal_to_values)
        super(EnumXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<enum/>'

    @staticmethod
    def marshal_from_values(item, index, libvirtxml):
        """Convert a EnumXML instance into a tag + attributes"""
        del index           # not used
        del libvirtxml      # not used
        if isinstance(item, str):
            return ("value", {}, item)
        else:
            raise xcepts.LibvirtXMLError("Expected a str attributes,"
                                         " not a %s" % str(item))

    @staticmethod
    def marshal_to_values(tag, attr_dict, index, libvirtxml, text):
        """Convert a tag + attributes into a EnumXML instance"""
        del attr_dict                # not used
        del index                    # not used
        if tag != 'value':
            return None
        newone = ValueXML(virsh_instance=libvirtxml.virsh)
        newone.value = text
        return newone
