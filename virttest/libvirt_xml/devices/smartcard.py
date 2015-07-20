"""
smartcard device support class(es)

http://libvirt.org/formatdomain.html#elementsSmartcard
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Smartcard(base.TypedDeviceBase):
    __slots__ = ('smartcard_type', 'smartcard_mode', 'source', 'source_mode',
                 'source_host', 'source_service', 'protocol', 'protocol_type',
                 'address', 'address_type', 'address_controller', 'address_slot')

    def __init__(self, type_name='spicevmc', virsh_instance=base.base.virsh):
        accessors.XMLAttribute('smartcard_type', self,
                               parent_xpath='/',
                               tag_name='smartcard',
                               attribute='type')
        accessors.XMLAttribute('smartcard_mode', self,
                               parent_xpath='/',
                               tag_name='smartcard',
                               attribute='mode')
        accessors.XMLElementDict('source', self,
                                 parent_xpath='/',
                                 tag_name='source')
        accessors.XMLAttribute('source_mode', self,
                               parent_xpath='/',
                               tag_name='source',
                               attribute='mode')
        accessors.XMLAttribute('source_host', self,
                               parent_xpath='/',
                               tag_name='source',
                               attribute='host')
        accessors.XMLAttribute('source_service', self,
                               parent_xpath='/',
                               tag_name='source',
                               attribute='service')
        accessors.XMLElementDict('protocol', self,
                                 parent_xpath='/',
                                 tag_name='protocol')
        accessors.XMLAttribute('protocol_type', self,
                               parent_xpath='/',
                               tag_name='protocol',
                               attribute='type')
        accessors.XMLElementDict('address', self,
                                 parent_xpath='/',
                                 tag_name='address')
        accessors.XMLAttribute('address_type', self,
                               parent_xpath='/',
                               tag_name='address',
                               attribute='type')
        accessors.XMLAttribute('address_controller', self,
                               parent_xpath='/',
                               tag_name='address',
                               attribute='controller')
        accessors.XMLAttribute('address_slot', self,
                               parent_xpath='/',
                               tag_name='address',
                               attribute='slot')
        super(Smartcard, self).__init__(device_tag='smartcard',
                                        type_name=type_name,
                                        virsh_instance=virsh_instance)
