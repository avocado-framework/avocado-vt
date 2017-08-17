"""
hostdev device support class(es)

http://libvirt.org/formatdomain.html#elementsHostDev
"""
from virttest.libvirt_xml.devices import base
from virttest.libvirt_xml import accessors


class Hostdev(base.TypedDeviceBase):

    __slots__ = ('mode', 'hostdev_type', 'source',
                 'managed', 'boot_order',)

    def __init__(self, type_name="hostdev", virsh_instance=base.base.virsh):
        accessors.XMLAttribute('hostdev_type', self, parent_xpath='/',
                               tag_name='hostdev', attribute='type')
        accessors.XMLAttribute('mode', self, parent_xpath='/',
                               tag_name='hostdev', attribute='mode')
        accessors.XMLAttribute('managed', self, parent_xpath='/',
                               tag_name='hostdev', attribute='managed')
        accessors.XMLElementNest('source', self, parent_xpath='/',
                                 tag_name='source', subclass=self.Source,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLAttribute('boot_order', self, parent_xpath='/',
                               tag_name='boot', attribute='order')

        super(Hostdev, self).__init__(device_tag='hostdev',
                                      type_name=type_name,
                                      virsh_instance=virsh_instance)

    def new_source(self, **dargs):
        new_one = self.Source(virsh_instance=self.virsh)
        if self.hostdev_type == 'pci':
            new_address = new_one.new_untyped_address(**dargs)
            new_one.untyped_address = new_address
        if self.hostdev_type == 'usb':
            new_one.vendor_id = dargs.pop("vendor_id", None)
            new_one.product_id = dargs.pop("product_id", None)
            new_address = new_one.new_untyped_address(**dargs)
            new_one.untyped_address = new_address
        if self.hostdev_type == 'scsi':
            new_one.adapter_name = dargs.pop("adapter_name", None)
            new_address = new_one.new_untyped_address(**dargs)
            new_one.untyped_address = new_address
        return new_one

    class Source(base.base.LibvirtXMLBase):

        __slots__ = ('untyped_address', 'vendor_id', 'product_id',
                     'adapter_name')

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLAttribute('vendor_id', self, parent_xpath='/',
                                   tag_name='vendor', attribute='id')
            accessors.XMLAttribute('product_id', self, parent_xpath='/',
                                   tag_name='product', attribute='id')
            accessors.XMLElementNest('untyped_address', self, parent_xpath='/',
                                     tag_name='address', subclass=self.UntypedAddress,
                                     subclass_dargs={
                                         'virsh_instance': virsh_instance})
            accessors.XMLAttribute('adapter_name', self, parent_xpath='/',
                                   tag_name='adapter', attribute='name')
            super(Hostdev.Source, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<source/>'

        def new_untyped_address(self, **dargs):
            new_one = self.UntypedAddress(virsh_instance=self.virsh)
            for key, value in dargs.items():
                setattr(new_one, key, value)
            return new_one

        class UntypedAddress(base.UntypedDeviceBase):

            __slots__ = ('device', 'domain', 'bus', 'slot', 'function',
                         'target', 'unit')

            def __init__(self, virsh_instance=base.base.virsh):
                accessors.XMLAttribute('domain', self, parent_xpath='/',
                                       tag_name='address', attribute='domain')
                accessors.XMLAttribute('slot', self, parent_xpath='/',
                                       tag_name='address', attribute='slot')
                accessors.XMLAttribute('bus', self, parent_xpath='/',
                                       tag_name='address', attribute='bus')
                accessors.XMLAttribute('device', self, parent_xpath='/',
                                       tag_name='address', attribute='device')
                accessors.XMLAttribute('function', self, parent_xpath='/',
                                       tag_name='address', attribute='function')
                accessors.XMLAttribute('target', self, parent_xpath='/',
                                       tag_name='address', attribute='target')
                accessors.XMLAttribute('unit', self, parent_xpath='/',
                                       tag_name='address', attribute='unit')
                super(Hostdev.Source.UntypedAddress, self).__init__(
                    "address", virsh_instance=virsh_instance)
                self.xml = "<address/>"
