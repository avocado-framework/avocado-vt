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
                                     'type_name': 'pci',
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementDict('alias', self,
                                 parent_xpath='/',
                                 tag_name='alias')
        super(Vsock, self).__init__(device_tag='vsock',
                                    virsh_instance=virsh_instance)
        self.xml = '<vsock/>'

    Address = librarian.get('address')

    def new_vsock_address(self, **dargs):
        """
        Return a new interface Address instance and set properties from dargs
        """
        new_one = self.Address("pci", virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one
