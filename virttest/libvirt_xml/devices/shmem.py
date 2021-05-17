"""
shared memory device support class(es)

<devices>
  <shmem name='my_shmem0' role='peer'>
    <model type='ivshmem-plain'/>
    <size unit='M'>4</size>
    <address type='pci' domain='0x0000' bus='0x00' slot='0x04' function='0x0'/>
  </shmem>
  <shmem name='shmem_server'>
    <model type='ivshmem-doorbell'/>
    <size unit='M'>2</size>
    <server path='/tmp/socket-shmem'/>
    <msi vectors='32' ioeventfd='on'/>
  </shmem>
</devices>

https://libvirt.org/formatdomain.html#shared-memory-device
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Shmem(base.UntypedDeviceBase):

    __slots__ = ('name', 'role', 'model_attrs',
                 'size', 'size_unit', 'pci_addr_attrs', 'server_attrs', 'msi_attrs', )

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute('name', self,
                               parent_xpath='/',
                               tag_name='shmem',
                               attribute='name')
        accessors.XMLAttribute('role', self,
                               parent_xpath='/',
                               tag_name='shmem',
                               attribute='role')
        accessors.XMLElementDict('model_attrs', self,
                                 parent_xpath='/',
                                 tag_name='model')
        accessors.XMLElementInt('size',
                                self, parent_xpath='/',
                                tag_name='size')
        accessors.XMLAttribute(property_name="size_unit",
                               libvirtxml=self,
                               forbidden=None,
                               parent_xpath='/',
                               tag_name='size',
                               attribute='unit')
        accessors.XMLElementDict('pci_addr_attrs', self,
                                 parent_xpath='/',
                                 tag_name='address')
        accessors.XMLElementDict('server_attrs', self,
                                 parent_xpath='/',
                                 tag_name='server')
        accessors.XMLElementDict('msi_attrs', self,
                                 parent_xpath='/output',
                                 tag_name='msi')
        super(Shmem, self).__init__(device_tag='shmem',
                                    virsh_instance=virsh_instance)
