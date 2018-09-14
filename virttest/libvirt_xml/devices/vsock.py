"""
vsock device support class(es)

https://libvirt.org/formatdomain.html#vsock
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base, librarian


class Vsock(base.UntypedDeviceBase):

    __slots__ = ('model_type', 'cid', 'address', 'alias')

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute('model_type', self,
                               parent_xpath='/',
                               tag_name='vsock',
                               attribute='model')
        accessors.XMLElementDict('cid', self,
                                 parent_xpath='/',
                                 tag_name='cid')
        accessors.XMLElementNest('address', self, parent_xpath='/',
                                 tag_name='address', subclass=self.Address,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementDict('alias', self,
                                 parent_xpath='/',
                                 tag_name='alias')
        super(Vsock, self).__init__(device_tag='vsock',
                                    virsh_instance=virsh_instance)
        self.xml = '<vsock/>'
    Address = librarian.get('address')
