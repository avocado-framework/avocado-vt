"""
nvram device support class(es)
  <nvram>
    <address type='spapr-vio' reg='0x00003000'/>
  </nvram>
https://libvirt.org/formatdomain.html#nvram-device
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Nvram(base.UntypedDeviceBase):

    __slots__ = ('address_type', 'address_reg')

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute('address_type', self,
                               parent_xpath='/',
                               tag_name='address',
                               attribute='type')
        accessors.XMLAttribute('address_reg', self,
                               parent_xpath='/',
                               tag_name='address',
                               attribute='reg')
        super(Nvram, self).__init__(device_tag='nvram',
                                    virsh_instance=virsh_instance)
