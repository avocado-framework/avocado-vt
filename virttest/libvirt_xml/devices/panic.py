"""
panic device support class(es)

http://libvirt.org/formatdomain.html#elementsPanic
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Panic(base.UntypedDeviceBase):

    __slots__ = ('model', 'addr_type', 'addr_iobase', 'addr_controller',
                 'addr_bus', 'addr_port')

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute('model', self, parent_xpath='/',
                               tag_name="panic", attribute='model')
        accessors.XMLAttribute('addr_type', self, parent_xpath='/',
                               tag_name="address", attribute='type')
        accessors.XMLAttribute('addr_iobase', self, parent_xpath='/',
                               tag_name="address", attribute='iobase')
        accessors.XMLAttribute('addr_controller', self, parent_xpath='/',
                               tag_name="address", attribute='controller')
        accessors.XMLAttribute('addr_bus', self, parent_xpath='/',
                               tag_name="address", attribute='bus')
        accessors.XMLAttribute('addr_port', self, parent_xpath='/',
                               tag_name="address", attribute='port')
        super(Panic, self).__init__(device_tag='panic',
                                    virsh_instance=virsh_instance)
