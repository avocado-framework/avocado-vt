"""
memory device support class(es)

"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base, librarian


class Memory(base.UntypedDeviceBase):

    __slots__ = ('mem_model', 'target', 'source', 'address')

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute('mem_model', self,
                               parent_xpath='/',
                               tag_name='memory',
                               attribute='model')
        accessors.XMLElementNest('target', self, parent_xpath='/',
                                 tag_name='target', subclass=self.Target,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest('source', self, parent_xpath='/',
                                 tag_name='source', subclass=self.Source,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest('address', self, parent_xpath='/',
                                 tag_name='address', subclass=self.Address,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        super(Memory, self).__init__(device_tag='memory', virsh_instance=virsh_instance)
        self.xml = '<memory/>'

    Address = librarian.get('address')

    class Target(base.base.LibvirtXMLBase):

        """
        Memory target xml class.

        Properties:

        size, node:
            int.
        size_unit:
            string.
        """
        __slots__ = ('size', 'size_unit', 'node')

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementInt('size',
                                    self, parent_xpath='/',
                                    tag_name='size')
            accessors.XMLAttribute(property_name="size_unit",
                                   libvirtxml=self,
                                   forbidden=None,
                                   parent_xpath='/',
                                   tag_name='size',
                                   attribute='unit')
            accessors.XMLElementInt('node',
                                    self, parent_xpath='/',
                                    tag_name='node')
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<target/>'

    class Source(base.base.LibvirtXMLBase):

        """
        Memory source xml class.

        Properties:

        pagesize:
            int.
        pagesize_unit, nodemask:
            string.
        """
        __slots__ = ('pagesize', 'pagesize_unit', 'nodemask')

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementInt('pagesize',
                                    self, parent_xpath='/',
                                    tag_name='pagesize')
            accessors.XMLAttribute(property_name="pagesize_unit",
                                   libvirtxml=self,
                                   forbidden=None,
                                   parent_xpath='/',
                                   tag_name='pagesize',
                                   attribute='unit')
            accessors.XMLElementText('nodemask',
                                     self, parent_xpath='/',
                                     tag_name='nodemask')
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<source/>'

    def new_mem_address(self, type_name='dimm', **dargs):
        """
        Return a new disk Address instance and set properties from dargs
        """
        new_one = self.Address(type_name=type_name, virsh_instance=self.virsh)
        for key, value in dargs.items():
            setattr(new_one, key, value)
        return new_one
