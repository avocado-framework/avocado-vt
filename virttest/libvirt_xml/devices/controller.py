"""
controller device support class(es)

http://libvirt.org/formatdomain.html#elementsControllers
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base, librarian


class Controller(base.TypedDeviceBase):

    __slots__ = ('type', 'index', 'model', 'ports', 'vectors', 'driver',
                 'address', 'pcihole64')

    def __init__(self, type_name, virsh_instance=base.base.virsh):
        super(Controller, self).__init__(device_tag='controller',
                                         type_name=type_name,
                                         virsh_instance=virsh_instance)
        accessors.XMLAttribute('type', self, parent_xpath='/',
                               tag_name='controller', attribute='type')
        accessors.XMLAttribute('index', self, parent_xpath='/',
                               tag_name='controller', attribute='index')
        accessors.XMLAttribute('model', self, parent_xpath='/',
                               tag_name='controller', attribute='model')
        accessors.XMLAttribute('ports', self, parent_xpath='/',
                               tag_name='controller', attribute='ports')
        accessors.XMLAttribute('vectors', self, parent_xpath='/',
                               tag_name='controller', attribute='vectors')
        accessors.XMLElementText('pcihole64', self, parent_xpath='/',
                                 tag_name='pcihole64')
        accessors.XMLElementDict('driver', self, parent_xpath='/',
                                 tag_name='driver')
        accessors.XMLElementNest('address', self, parent_xpath='/',
                                 tag_name='address', subclass=self.Address,
                                 subclass_dargs={'type_name': 'pci',
                                                 'virsh_instance': virsh_instance})

    Address = librarian.get('address')

    def new_controller_address(self, **dargs):
        """
        Return a new controller Address instance and set properties from dargs
        """
        new_one = self.Address("pci", virsh_instance=self.virsh)
        for key, value in dargs.items():
            setattr(new_one, key, value)
        return new_one
