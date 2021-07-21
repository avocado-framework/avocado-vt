"""
disk device support class(es)

http://libvirt.org/formatdomain.html#elementsDisks
"""

from virttest.libvirt_xml import accessors, xcepts
from virttest.libvirt_xml.devices import base, librarian


class Disk(base.TypedDeviceBase):

    """
    Disk device XML class

    Properties:
        device:
            string, how exposted to guest
        rawio:
            string (yes/no), disk needs rawio capability
        sharebacking:
            string (yes/no), support share base image of transient disk
        sgio:
            string, "filtered" or "unfiltered"
        snapshot:
            string, "yes", "no", "internal" or "external"
        wwn:
            string.
        serial:
            string.
        vendor:
            string.
        product:
            string.
        driver:
            dict, keys: name, type, cache, error_policy, io, ioeventfd,
            event_idx, copy_on_read, discard
        target:
            dict, keys: dev, bus, tray
        alias:
            dict, keys: name
        blockio:
            dict, keys: logical_block_size, physical_block_size
        geometry:
            dict, keys: cyls, heads, secs, trans
        address:
            libvirt_xml.devices.Address instance
        boot:
            string, boot order number to use if not using boot in os element
        loadparm:
            string, loadparm attribute on disk's boot element
        readonly:
            bool, True/False
        transient:
            bool, True/False
        share:
            bool, True/False
        mirror:
            bool, read-only, True if block copy started
        ready:
            bool, read-only, True if disk ready for pivot
        iotune:
            libvirt_xml.devices.Disk.IOTune instance
        source:
            libvirt_xml.devices.Disk.DiskSource instance
        encryption:
            libvirt_xml.devices.Disk.Encryption instance.
        auth:
            libvirt_xml.devices.Disk.Auth instance.
        reservations:
            libvirt_xml.devices.Disk.Reservations instance.
        drivermetadata:
            libvirt_xml.devices.Disk.DriverMetadata instance.
   """

    __slots__ = ('device', 'rawio', 'sgio', 'snapshot', 'driver', 'target', 'alias',
                 'address', 'boot', 'loadparm', 'readonly', 'transient', 'share', 'model',
                 'mirror', 'ready', 'iotune', 'source', 'blockio', 'geometry',
                 'wwn', 'serial', 'vendor', 'product', 'encryption', 'auth',
                 'reservations', 'backingstore', 'drivermetadata', 'sharebacking')

    def __init__(self, type_name='file', virsh_instance=base.base.virsh):
        accessors.XMLAttribute('device', self, parent_xpath='/',
                               tag_name='disk', attribute='device')
        accessors.XMLAttribute('model', self, parent_xpath='/',
                               tag_name='disk', attribute='model')
        accessors.XMLAttribute('rawio', self, parent_xpath='/',
                               tag_name='disk', attribute='rawio')
        accessors.XMLAttribute('sharebacking', self, parent_xpath='/',
                               tag_name='transient', attribute='shareBacking')
        accessors.XMLAttribute('sgio', self, parent_xpath='/',
                               tag_name='disk', attribute='sgio')
        accessors.XMLAttribute('snapshot', self, parent_xpath='/',
                               tag_name='disk', attribute='snapshot')
        accessors.XMLElementText('wwn', self, parent_xpath='/',
                                 tag_name='wwn')
        accessors.XMLElementText('serial', self, parent_xpath='/',
                                 tag_name='serial')
        accessors.XMLElementText('vendor', self, parent_xpath='/',
                                 tag_name='vendor')
        accessors.XMLElementText('product', self, parent_xpath='/',
                                 tag_name='product')
        accessors.XMLElementDict('driver', self, parent_xpath='/',
                                 tag_name='driver')
        accessors.XMLElementDict('target', self, parent_xpath='/',
                                 tag_name='target')
        accessors.XMLElementDict('alias', self, parent_xpath='/',
                                 tag_name='alias')
        accessors.XMLElementDict('blockio', self, parent_xpath='/',
                                 tag_name='blockio')
        accessors.XMLElementDict('geometry', self, parent_xpath='/',
                                 tag_name='geometry')
        accessors.XMLElementNest('address', self, parent_xpath='/',
                                 tag_name='address', subclass=self.Address,
                                 subclass_dargs={'type_name': 'drive',
                                                 'virsh_instance': virsh_instance})
        accessors.XMLAttribute('boot', self, parent_xpath='/',
                               tag_name='boot', attribute='order')
        accessors.XMLAttribute('loadparm', self, parent_xpath='/',
                               tag_name='boot', attribute='loadparm')
        accessors.XMLElementBool('readonly', self, parent_xpath='/',
                                 tag_name='readonly')
        accessors.XMLElementBool('transient', self, parent_xpath='/',
                                 tag_name='transient')
        accessors.XMLElementBool('share', self, parent_xpath='/',
                                 tag_name='shareable')
        accessors.XMLElementNest('source', self, parent_xpath='/',
                                 tag_name='source', subclass=self.DiskSource,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        ro = ['set', 'del']
        accessors.XMLElementBool('mirror', self, forbidden=ro,
                                 parent_xpath='/', tag_name='mirror')
        accessors.XMLElementBool('ready', self, forbidden=ro,
                                 parent_xpath='/', tag_name='ready')
        accessors.XMLElementNest('iotune', self, parent_xpath='/',
                                 tag_name='iotune', subclass=self.IOTune,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest('encryption', self, parent_xpath='/',
                                 tag_name='encryption', subclass=self.Encryption,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest('auth', self, parent_xpath='/',
                                 tag_name='auth', subclass=self.Auth,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest('reservations', self, parent_xpath='/',
                                 tag_name='reservations',
                                 subclass=Disk.Reservations,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest('backingstore', self, parent_xpath='/',
                                 tag_name='backingStore',
                                 subclass=self.BackingStore,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest('drivermetadata', self, parent_xpath='/',
                                 tag_name='driver',
                                 subclass=self.DriverMetadata,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        super(Disk, self).__init__(device_tag='disk', type_name=type_name,
                                   virsh_instance=virsh_instance)

    def new_disk_source(self, **dargs):
        """
        Return a new disk source instance and set properties from dargs
        """
        new_one = self.DiskSource(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_iotune(self, **dargs):
        """
        Return a new disk IOTune instance and set properties from dargs
        """
        new_one = self.IOTune(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_encryption(self, **dargs):
        """
        Return a new disk encryption instance and set properties from dargs
        """
        new_one = self.Encryption(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_disk_address(self, type_name='drive', **dargs):
        """
        Return a new disk Address instance and set properties from dargs
        """
        new_one = self.Address(type_name=type_name, virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_auth(self, **dargs):
        """
        Return a new disk auth instance and set properties from dargs
        """
        new_one = self.Auth(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_reservations(self, **dargs):
        """
        Return a new disk reservations instance and set properties from dargs
        """
        new_one = self.Reservations(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_slices(self, **dargs):
        """
        Return a new disk slices instance and set properties from dargs
        """
        new_one = self.Slices(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_backingstore(self, **dargs):
        """
        Return a new disk backingstore instance and set properties from dargs
        """
        new_one = self.BackingStore(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def get_backingstore_list(self):
        """
        Usage: get source file attribute from backingStore
            test_disk = Disk()
            backingstore_list = test_disk.get_backingstore_list()
            source_file_list = [elem.find('source').get('file') or elem.find('source').get('name') for elem in backingstore_list]

        :return: a disk backingstore list where each element is primitive virttest.element_tree._ElementInterface object
        """
        backingstore_list = []
        for elem in self.xmltreefile.getiterator('backingStore'):
            backingstore_list.append(elem)
        return backingstore_list

    def new_drivermetadata(self, **dargs):
        """
        Return a new DriverMetadata instance and set properties from dargs
        """
        new_one = self.DriverMetadata(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def get_all_backingstore(self):
        """
        Get all backingstore of a Disk object

        :return: an ordered list of backingstore items
        """

        def _get_next_backingstore(elem):
            """
            Recursively get backingstore object

            :param elem: root element to get backingstore object
            """
            if elem.xmltreefile.find('/backingStore') is None:
                return
            bs = elem.backingstore
            backingstore_list.append(bs)
            _get_next_backingstore(bs)

        backingstore_list = []
        _get_next_backingstore(self)

        return backingstore_list

    # For convenience
    Address = librarian.get('address')

    class DiskSource(base.base.LibvirtXMLBase):

        """
        Disk source device XML class

        Properties:

        attrs: Dictionary of attributes, qualifying the disk type
        seclabels: list of libvirt_xml.devices.seclabel.Seclabel instances
        hosts: list of dictionaries describing network host properties
        """

        __slots__ = ('attrs', 'seclabels', 'hosts', 'encryption', 'auth',
                     'reservations', 'slices', 'config_file', 'snapshot_name')

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementDict('attrs', self, parent_xpath='/',
                                     tag_name='source')
            accessors.XMLElementList('seclabels', self, parent_xpath='/',
                                     marshal_from=self.marshal_from_seclabel,
                                     marshal_to=self.marshal_to_seclabel)
            accessors.XMLElementList('hosts', self, parent_xpath='/',
                                     marshal_from=self.marshal_from_host,
                                     marshal_to=self.marshal_to_host)
            accessors.XMLElementNest('encryption', self, parent_xpath='/',
                                     tag_name='encryption',
                                     subclass=Disk.Encryption,
                                     subclass_dargs={
                                         'virsh_instance': virsh_instance})
            accessors.XMLElementNest('auth', self, parent_xpath='/',
                                     tag_name='auth', subclass=Disk.Auth,
                                     subclass_dargs={
                                         'virsh_instance': virsh_instance})
            accessors.XMLElementNest('reservations', self, parent_xpath='/',
                                     tag_name='reservations',
                                     subclass=Disk.Reservations,
                                     subclass_dargs={
                                         'virsh_instance': virsh_instance})
            accessors.XMLElementNest('slices', self, parent_xpath='/',
                                     tag_name='slices',
                                     subclass=Disk.Slices,
                                     subclass_dargs={
                                         'virsh_instance': virsh_instance})
            accessors.XMLAttribute('config_file', self, parent_xpath='/',
                                   tag_name='config', attribute='file')
            accessors.XMLAttribute('snapshot_name', self, parent_xpath='/',
                                   tag_name='snapshot', attribute='name')
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<source/>'

        @staticmethod
        def marshal_from_seclabel(item, index, libvirtxml):
            """Convert a Seclabel instance into tag + attributes"""
            del index           # not used
            del libvirtxml      # not used
            root = item.xmltreefile.getroot()
            if root.tag == 'seclabel':
                new_dict = dict(list(root.items()))
                text_dict = {}
                # Put element text into dict under key 'text'
                for key in ('label', 'baselabel'):
                    text_val = item.xmltreefile.findtext(key)
                    if text_val:
                        text_dict.update({key: text_val})
                if text_dict:
                    new_dict['text'] = text_dict
                return (root.tag, new_dict)
            else:
                raise xcepts.LibvirtXMLError("Expected a list of seclabel "
                                             "instances, not a %s" % str(item))

        @staticmethod
        def marshal_to_seclabel(tag, attr_dict, index, libvirtxml):
            """Convert a tag + attributes into a Seclabel instance"""
            del index           # not used
            if tag != 'seclabel':
                return None     # Don't convert this item
            Seclabel = librarian.get('seclabel')
            newone = Seclabel(virsh_instance=libvirtxml.virsh)
            newone.update(attr_dict)
            return newone

        @staticmethod
        def marshal_from_host(item, index, libvirtxml):
            """Convert a dictionary into a tag + attributes"""
            del index           # not used
            del libvirtxml      # not used
            if not isinstance(item, dict):
                raise xcepts.LibvirtXMLError("Expected a dictionary of host "
                                             "attributes, not a %s"
                                             % str(item))
            return ('host', dict(item))  # return copy of dict, not reference

        @staticmethod
        def marshal_to_host(tag, attr_dict, index, libvirtxml):
            """Convert a tag + attributes into a dictionary"""
            del index                    # not used
            del libvirtxml               # not used
            if tag != 'host':
                return None              # skip this one
            return dict(attr_dict)       # return copy of dict, not reference

    class IOTune(base.base.LibvirtXMLBase):

        """
        IOTune device XML class

        Properties:

        total_bytes_sec: str(int)
        read_bytes_sec: str(int)
        write_bytes_sec: str(int)
        total_iops_sec: str(int)
        read_iops_sec: str(int)
        write_iops_sec: str(int)
        """

        __slots__ = ('total_bytes_sec', 'read_bytes_sec', 'write_bytes_sec',
                     'total_iops_sec', 'read_iops_sec', 'write_iops_sec')

        def __init__(self, virsh_instance=base.base.virsh):
            # pylint: disable=E1133,E1135
            for slot in self.__all_slots__:
                if slot in base.base.LibvirtXMLBase.__all_slots__:
                    continue    # don't add these
                else:
                    accessors.XMLElementInt(slot, self, parent_xpath='/',
                                            tag_name=slot)
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<iotune/>'

    class Encryption(base.base.LibvirtXMLBase):

        """
        Encryption device XML class

        Properties:

        encryption:
            string.
        secret:
            dict, keys: type, uuid
        """

        __slots__ = ('encryption', 'secret')

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLAttribute('encryption', self, parent_xpath='/',
                                   tag_name='encryption', attribute='format')
            accessors.XMLElementDict('secret', self, parent_xpath='/',
                                     tag_name='secret')
            super(self.__class__, self).__init__(
                virsh_instance=virsh_instance)
            self.xml = '<encryption/>'

    class Auth(base.base.LibvirtXMLBase):

        """
        Auth device XML class

        Properties:

        auth_user:
            string, attribute of auth tag
        secret_type:
            string, attribute of secret tag, sub-tag of the auth tag
        secret_uuid:
            string, attribute of secret tag, sub-tag of the auth tag
        secret_usage:
            string, attribute of secret tag, sub-tag of the auth tag
        """

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
            self.xml = '<auth/>'

    class Slices(base.base.LibvirtXMLBase):

        """
        slices device XML class
        Typical xml looks like:
        <slices>
          <slice type='storage' offset='12345' size='123'/>
        </slices>
        Properties:

        slice_type:
            string, type attribute of slice tag
        slice_offset:
            string, offset attribute of slice tag
        slice_size:
            string, size attribute of slice tag
        """

        __slots__ = ('slice_type', 'slice_offset', 'slice_size')

        def __init__(self, virsh_instance=base.base.virsh, auth_user=""):
            accessors.XMLAttribute('slice_type', self, parent_xpath='/',
                                   tag_name='slice', attribute='type')
            accessors.XMLAttribute('slice_offset', self, parent_xpath='/',
                                   tag_name='slice', attribute='offset')
            accessors.XMLAttribute('slice_size', self, parent_xpath='/',
                                   tag_name='slice', attribute='size')
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<slices/>'

    class Reservations(base.base.LibvirtXMLBase):

        """
        Reservations device XML class

        Properties:

        reservations_managed:
            string, attribute of reservations tag
        reservations_source_type:
            string, attribute of source tag, sub-tag of the reservations tag
        reservations_source_path:
            string, attribute of source tag, sub-tag of the reservations tag
        reservations_source_mode:
            string, attribute of source tag, sub-tag of the reservations tag
        """

        __slots__ = ('reservations_managed', 'reservations_source_type',
                     'reservations_source_path', 'reservations_source_mode')

        def __init__(self, virsh_instance=base.base.virsh, reservations_managed=""):
            accessors.XMLAttribute('reservations_managed', self, parent_xpath='/',
                                   tag_name='reservations', attribute='managed')
            accessors.XMLAttribute('reservations_source_type', self, parent_xpath='/',
                                   tag_name='source', attribute='type')
            accessors.XMLAttribute('reservations_source_path', self, parent_xpath='/',
                                   tag_name='source', attribute='path')
            accessors.XMLAttribute('reservations_source_mode', self, parent_xpath='/',
                                   tag_name='source', attribute='mode')
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<reservations/>'

    class BackingStore(base.base.LibvirtXMLBase):
        """
        BakingStore of disk device XML class

        type:
            string, attribute of backingStore tag
        index:
            string, attribute of backingStore tag
        format:
            dict, key-attribute of backingStore tag
        source:
            nested xml of backingStore tag
        """
        __slots__ = ('type', 'index', 'format', 'source', 'backingstore')

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLAttribute('type', self,
                                   parent_xpath='/',
                                   tag_name='backingStore',
                                   attribute='type')
            accessors.XMLAttribute('index', self,
                                   parent_xpath='/',
                                   tag_name='backingStore',
                                   attribute='index')
            accessors.XMLElementDict('format', self,
                                     parent_xpath='/',
                                     tag_name='format')
            accessors.XMLElementNest('source', self,
                                     parent_xpath='/',
                                     tag_name='source',
                                     subclass=self.Source,
                                     subclass_dargs={
                                         'virsh_instance': virsh_instance})
            accessors.XMLElementNest('backingstore', self, parent_xpath='/',
                                     tag_name='backingStore',
                                     subclass=Disk.BackingStore,
                                     subclass_dargs={
                                         'virsh_instance': virsh_instance})

            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<backingStore/>'

        def new_source(self, **dargs):
            """
            Create new source for backingstore

            """
            new_one = self.Source(virsh_instance=self.virsh)
            for key, value in list(dargs.items()):
                setattr(new_one, key, value)
            return new_one

        class Source(base.base.LibvirtXMLBase):
            """
            Source of backingstore xml class

            dev:
                string, attribute of backingStore/source tag
            protocal:
                string, attribute of backingStore/source tag
            name:
                string, attribute of backingStore/source tag
            host:
                dict, nested xml of backingStore/source tag
            file:
                string, attribute of backingStore/source tag
            """

            __slots__ = ('attrs', 'dev', 'protocol', 'name', 'host', 'file', 'auth')

            def __init__(self, virsh_instance=base.base.virsh):
                accessors.XMLElementDict('attrs', self,
                                         parent_xpath='/',
                                         tag_name='source')
                accessors.XMLAttribute('dev', self,
                                       parent_xpath='/',
                                       tag_name='source',
                                       attribute='dev')
                accessors.XMLAttribute('protocol', self,
                                       parent_xpath='/',
                                       tag_name='source',
                                       attribute='protocol')
                accessors.XMLAttribute('name', self,
                                       parent_xpath='/',
                                       tag_name='source',
                                       attribute='name')
                accessors.XMLElementDict('host', self,
                                         parent_xpath='/',
                                         tag_name='host')
                accessors.XMLAttribute('file', self,
                                       parent_xpath='/',
                                       tag_name='source',
                                       attribute='file')
                accessors.XMLElementNest('auth', self,
                                         parent_xpath='/',
                                         tag_name='auth',
                                         subclass=Disk.Auth,
                                         subclass_dargs={
                                            'virsh_instance': virsh_instance})

                super(self.__class__, self).__init__(virsh_instance=virsh_instance)
                self.xml = '<source/>'

    class DriverMetadata(base.base.LibvirtXMLBase):

        """
        DriverMetaData XML class

        <driver name='qemu' type='qcow2'>
         <metadata_cache>
           <max_size unit='bytes'>10</max_size>
         </metadata_cache>
        </driver>

        Properties:

        attrs: Dictionary of attributes, qualifying the driver name and type,etc.
        metadata_cache: embedded class to describe metadata attributes
        usages:
            custom_disk = Disk(type_name='disk')
            driver_dict = {"name": "qemu","type": "qcow2"}
            new_one = custom_disk.new_drivermetadata(**{"attrs": driver_dict})

            metadata_cache_dict = {"max_size": "10", "max_size_unit": "bytes"}

            new_one.metadata_cache = custom_disk.DriverMetadata().new_metadatacache(**metadata_cache_dict)

            custom_disk.drivermetadata = new_one
        """

        __slots__ = ('attrs', 'metadata_cache')

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementDict('attrs', self, parent_xpath='/',
                                     tag_name='driver')
            accessors.XMLElementNest('metadata_cache', self, parent_xpath='/',
                                     tag_name='metadata_cache',
                                     subclass=self.MetadataCache,
                                     subclass_dargs={
                                         'virsh_instance': virsh_instance})
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<driver/>'

        def new_metadatacache(self, **dargs):
            """
            Create new MetadataCache for DriverMetadata

            """
            new_one = self.MetadataCache(virsh_instance=self.virsh)
            for key, value in list(dargs.items()):
                setattr(new_one, key, value)
            return new_one

        class MetadataCache(base.base.LibvirtXMLBase):
            """
            Source of MetadataCache xml class

            max_size:
                string, attribute of MetadataCache max size
            max_size_unit:
                string, attribute of MetadataCache max size unit
            """

            __slots__ = ('max_size', 'max_size_unit')

            def __init__(self, virsh_instance=base.base.virsh):
                accessors.XMLElementText(property_name='max_size',
                                         libvirtxml=self,
                                         parent_xpath='/',
                                         tag_name='max_size')
                accessors.XMLAttribute(property_name="max_size_unit",
                                       libvirtxml=self,
                                       parent_xpath='/',
                                       tag_name='max_size',
                                       attribute='unit')
                super(self.__class__, self).__init__(virsh_instance=virsh_instance)
                self.xml = '<metadata_cache/>'
