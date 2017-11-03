"""
lease device support class(es)

http://libvirt.org/formatdomain.html#elementsLease
"""

from virttest.libvirt_xml.devices import base
from virttest.libvirt_xml import accessors


class Lease(base.UntypedDeviceBase):
    __slots__ = ('lockspace', 'key', 'target')

    def __init__(self, virsh_instance=base.base.virsh):
        # example for lease : lockspace, key and target
        #
        # <lease>
        #   <lockspace>somearea</lockspace>
        #   <key>somekey</key>
        #   <target path='/some/lease/path' offset='1024'/>
        # </lease>
        accessors.XMLElementText('lockspace', self,
                                 parent_xpath='/',
                                 tag_name='lockspace')
        accessors.XMLElementText('key', self,
                                 parent_xpath='/',
                                 tag_name='key')
        accessors.XMLElementDict('target', self, parent_xpath='/',
                                 tag_name='target')
        super(Lease, self).__init__(device_tag='lease',
                                    virsh_instance=virsh_instance)
