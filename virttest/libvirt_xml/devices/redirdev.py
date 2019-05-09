"""
redirdev device support class(es)

http://libvirt.org/formatdomain.html#elementsRedir
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base, librarian


class Redirdev(base.TypedDeviceBase):

    __slots__ = ('type', 'bus', 'source', 'protocol', 'boot', 'alias', 'address')

    def __init__(self, type_name="redirdev", virsh_instance=base.base.virsh):
        super(Redirdev, self).__init__(device_tag='redirdev',
                                       type_name=type_name,
                                       virsh_instance=virsh_instance)
        accessors.XMLAttribute('type', self, parent_xpath='/',
                               tag_name='redirdev', attribute='type')
        accessors.XMLAttribute('bus', self, parent_xpath='/',
                               tag_name='redirdev', attribute='bus')
        accessors.XMLElementNest('source', self, parent_xpath='/',
                                 tag_name='source', subclass=self.Source,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementDict('protocol', self, parent_xpath='/',
                                 tag_name='protocol')
        accessors.XMLElementDict('boot', self, parent_xpath='/',
                                 tag_name='boot')
        accessors.XMLElementDict('alias', self, parent_xpath='/',
                                 tag_name='alias')
        accessors.XMLElementNest('address', self, parent_xpath='/',
                                 tag_name='address', subclass=self.Address,
                                 subclass_dargs={'type_name': 'usb',
                                                 'virsh_instance': virsh_instance})
    Address = librarian.get('address')

    def new_source(self, **dargs):
        """
        Return a new Redirdev Source instance and set properties from dargs
        """
        new_one = self.Source(virsh_instance=self.virsh)
        for k, v in dargs.items():
            if v:
                setattr(new_one, k, v)
        return new_one

    class Source(base.base.LibvirtXMLBase):

        __slots__ = ('mode', 'host', 'service', 'tls', 'path')

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLAttribute('mode', self, parent_xpath='/',
                                   tag_name='source', attribute='mode')
            accessors.XMLAttribute('host', self, parent_xpath='/',
                                   tag_name='source', attribute='host')
            accessors.XMLAttribute('service', self, parent_xpath='/',
                                   tag_name='source', attribute='service')
            accessors.XMLAttribute('tls', self, parent_xpath='/',
                                   tag_name='source', attribute='tls')
            accessors.XMLAttribute('path', self, parent_xpath='/',
                                   tag_name='source', attribute='path')
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<source/>'
