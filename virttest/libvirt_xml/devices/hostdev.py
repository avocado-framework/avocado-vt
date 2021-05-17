"""
hostdev device support class(es)

http://libvirt.org/formatdomain.html#elementsHostDev
"""
from virttest.libvirt_xml.devices import base
from virttest.libvirt_xml import accessors


class Hostdev(base.TypedDeviceBase):

    __slots__ = ('type', 'mode', 'managed', 'sgio', 'rawio',
                 'source', 'boot_order', 'readonly', 'shareable',
                 'alias', 'model', 'teaming')

    def __init__(self, type_name="hostdev", virsh_instance=base.base.virsh):
        accessors.XMLAttribute('type', self, parent_xpath='/',
                               tag_name='hostdev', attribute='type')
        accessors.XMLAttribute('mode', self, parent_xpath='/',
                               tag_name='hostdev', attribute='mode')
        accessors.XMLAttribute('model', self, parent_xpath='/',
                               tag_name='hostdev', attribute='model')
        accessors.XMLAttribute('managed', self, parent_xpath='/',
                               tag_name='hostdev', attribute='managed')
        accessors.XMLAttribute('sgio', self, parent_xpath='/',
                               tag_name='hostdev', attribute='sgio')
        accessors.XMLAttribute('rawio', self, parent_xpath='/',
                               tag_name='hostdev', attribute='rawio')
        accessors.XMLElementNest('source', self, parent_xpath='/',
                                 tag_name='source', subclass=self.Source,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLAttribute('boot_order', self, parent_xpath='/',
                               tag_name='boot', attribute='order')
        accessors.XMLElementBool('readonly', self, parent_xpath='/',
                                 tag_name='readonly')
        accessors.XMLElementBool('shareable', self, parent_xpath='/',
                                 tag_name='shareable')
        accessors.XMLElementDict('alias', self, parent_xpath='/',
                                 tag_name='alias')
        accessors.XMLElementDict("teaming", self, parent_xpath='/',
                                 tag_name='teaming')
        super(self.__class__, self).__init__(device_tag='hostdev',
                                             type_name=type_name,
                                             virsh_instance=virsh_instance)

    def new_source(self, **dargs):
        new_one = self.Source(virsh_instance=self.virsh)
        if self.type == 'pci':
            pass
        elif self.type == 'usb':
            new_one.vendor_id = dargs.pop("vendor_id", None)
            new_one.product_id = dargs.pop("product_id", None)
            new_one.address_bus = dargs.pop("address_bus", None)
            new_one.address_device = dargs.pop("address_device", None)
        elif self.type == 'scsi':
            if dargs.get("adapter_name"):
                new_one.adapter_name = dargs.pop("adapter_name")
            if dargs.get("protocol"):
                new_one.protocol = dargs.pop("protocol")
            if dargs.get("source_name"):
                new_one.source_name = dargs.pop("source_name")
            if dargs.get("host_name"):
                new_one.host_name = dargs.pop("host_name")
            if dargs.get("host_port"):
                new_one.host_port = dargs.pop("host_port")
            auth_args = {'auth_user': dargs.pop('auth_user', None),
                         'secret_type': dargs.pop('secret_type', None),
                         'secret_uuid': dargs.pop('secret_uuid', None),
                         'secret_usage': dargs.pop('secret_usage', None)
                         }
            if auth_args['auth_user']:
                new_auth = new_one.new_auth(**auth_args)
                new_one.auth = new_auth
            initiator_args = {'iqn_id': dargs.pop('iqn_id', None)}
            if initiator_args['iqn_id']:
                new_initiator = new_one.new_initiator(**initiator_args)
                new_one.initiator = new_initiator
        if dargs:
            new_address = new_one.new_untyped_address(**dargs)
            new_one.untyped_address = new_address
        return new_one

    class Source(base.base.LibvirtXMLBase):

        __slots__ = ('untyped_address', 'vendor_id', 'product_id',
                     'adapter_name', 'protocol', 'source_name',
                     'host_name', 'host_port', 'auth', 'address_bus',
                     'address_device', 'initiator')

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
            accessors.XMLAttribute('protocol', self, parent_xpath='/',
                                   tag_name='source', attribute='protocol')
            accessors.XMLAttribute('source_name', self, parent_xpath='/',
                                   tag_name='source', attribute='name')
            accessors.XMLAttribute('host_name', self, parent_xpath='/',
                                   tag_name='host', attribute='name')
            accessors.XMLAttribute('host_port', self, parent_xpath='/',
                                   tag_name='host', attribute='port')
            accessors.XMLAttribute('address_bus', self, parent_xpath='/',
                                   tag_name='address', attribute='bus')
            accessors.XMLAttribute('address_device', self, parent_xpath='/',
                                   tag_name='address', attribute='device')
            accessors.XMLElementNest('auth', self, parent_xpath='/',
                                     tag_name='auth', subclass=self.Auth,
                                     subclass_dargs={
                                         'virsh_instance': virsh_instance})
            accessors.XMLElementNest('initiator', self, parent_xpath='/',
                                     tag_name='initiator', subclass=self.Initiator,
                                     subclass_dargs={
                                         'virsh_instance': virsh_instance})
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<source/>'

        def new_untyped_address(self, **dargs):
            new_one = self.UntypedAddress(virsh_instance=self.virsh)
            for key, value in list(dargs.items()):
                if value:
                    setattr(new_one, key, value)
            return new_one

        def new_auth(self, **dargs):
            new_one = self.Auth(virsh_instance=self.virsh)
            for key, value in list(dargs.items()):
                if value:
                    setattr(new_one, key, value)
            return new_one

        def new_initiator(self, **dargs):
            new_one = self.Initiator(virsh_instance=self.virsh)
            for key, value in list(dargs.items()):
                if value:
                    setattr(new_one, key, value)
            return new_one

        class UntypedAddress(base.UntypedDeviceBase):

            __slots__ = ('device', 'domain', 'bus', 'slot', 'function',
                         'target', 'unit', 'uuid')

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
                accessors.XMLAttribute('uuid', self, parent_xpath='/',
                                       tag_name='address', attribute='uuid')
                super(self.__class__, self).__init__(
                    "address", virsh_instance=virsh_instance)
                self.xml = "<address/>"

        class Auth(base.base.LibvirtXMLBase):

            __slots__ = ('auth_user', 'secret_type', 'secret_uuid', 'secret_usage')

            def __init__(self, virsh_instance=base.base.virsh, auth_user=""):
                accessors.XMLAttribute('auth_user', self, parent_xpath='/',
                                       tag_name='auth', attribute='username')
                accessors.XMLAttribute('secret_type', self, parent_xpath='/',
                                       tag_name='secret', attribute='type')
                accessors.XMLAttribute('secret_uuid', self, parent_xpath='/',
                                       tag_name='secret', attribute='uuid')
                accessors.XMLAttribute('secret_usage', self, parent_xpath='/',
                                       tag_name='secret', attribute='usage')
                super(self.__class__, self).__init__(virsh_instance=virsh_instance)
                self.xml = "<auth/>"

        class Initiator(base.base.LibvirtXMLBase):

            __slots__ = ('iqn_id',)

            def __init__(self, virsh_instance=base.base.virsh, auth_user=""):
                accessors.XMLAttribute('iqn_id', self, parent_xpath='/',
                                       tag_name='iqn', attribute='name')
                super(self.__class__, self).__init__(virsh_instance=virsh_instance)
                self.xml = "<initiator/>"
