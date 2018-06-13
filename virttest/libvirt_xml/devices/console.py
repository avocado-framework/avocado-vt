"""
Console device support class(es)

http://libvirt.org/formatdomain.html#elementCharSerial
"""

from virttest.libvirt_xml import base, accessors, xcepts
from virttest.libvirt_xml.devices.character import CharacterBase


class Console(CharacterBase):

    __slots__ = ('protocol_type', 'target_port', 'target_type', 'sources',
                 'alias')

    def __init__(self, type_name='pty', virsh_instance=base.virsh):
        accessors.XMLAttribute('protocol_type', self, parent_xpath='/',
                               tag_name='protocol', attribute='type')
        accessors.XMLAttribute('target_port', self, parent_xpath='/',
                               tag_name='target', attribute='port')
        accessors.XMLAttribute('target_type', self, parent_xpath='/',
                               tag_name='target', attribute='type')
        accessors.XMLElementList('sources', self, parent_xpath='/',
                                 marshal_from=self.marshal_from_sources,
                                 marshal_to=self.marshal_to_sources)
        accessors.XMLElementDict('alias', self, parent_xpath='/',
                                 tag_name='alias')
        super(
            Console, self).__init__(device_tag='console', type_name=type_name,
                                    virsh_instance=virsh_instance)

    @staticmethod
    def marshal_from_sources(item, index, libvirtxml):
        """
        Convert a dict to console source attributes.
        """
        del index
        del libvirtxml
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of source "
                                         "attributes, not a %s"
                                         % str(item))
        return ('source', dict(item))

    @staticmethod
    def marshal_to_sources(tag, attr_dict, index, libvirtxml):
        """
        Convert a source tag and attributes to a dict.
        """
        del index
        del libvirtxml
        if tag != 'source':
            return None
        return dict(attr_dict)
