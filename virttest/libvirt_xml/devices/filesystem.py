"""
filesystem device support class(es)

https://libvirt.org/formatdomain.html#elementsFilesystem
"""

from virttest.libvirt_xml.devices import base
from virttest.libvirt_xml import accessors


class Filesystem(base.TypedDeviceBase):

    __slots__ = ('accessmode', 'source', 'target', 'driver', 'binary', 'alias')

    def __init__(self, type_name='mount', virsh_instance=base.base.virsh):
        accessors.XMLAttribute('accessmode', self, parent_xpath='/',
                               tag_name='filesystem', attribute='accessmode')
        accessors.XMLElementDict('source', self, parent_xpath='/',
                                 tag_name='source')
        accessors.XMLElementDict('target', self, parent_xpath='/',
                                 tag_name='target')
        accessors.XMLElementDict('driver', self,
                                 parent_xpath='/',
                                 tag_name='driver')
        accessors.XMLElementNest('binary', self, parent_xpath='/',
                                 tag_name='binary', subclass=self.Binary,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementDict('alias', self,
                                 parent_xpath='/',
                                 tag_name='alias')
        super(Filesystem, self).__init__(device_tag='filesystem',
                                         type_name=type_name,
                                         virsh_instance=virsh_instance)

    class Binary(base.base.LibvirtXMLBase):

        """
        Filesystem binary subclass
        Typical xml looks like:
        <binary path='/usr/libexec/virtiofsd' xattr='on'>
            <cache mode='always'/>
            <lock posix='on' flock='on'/>
        </binary>
        """
        __slots__ = ('path', 'xattr', 'cache_mode', 'lock_posix', 'flock')

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLAttribute('path', self,
                                   parent_xpath='/',
                                   tag_name='binary',
                                   attribute='path')
            accessors.XMLAttribute('xattr', self,
                                   parent_xpath='/',
                                   tag_name='binary',
                                   attribute='xattr')
            accessors.XMLAttribute('cache_mode', self,
                                   parent_xpath='/',
                                   tag_name='cache',
                                   attribute='mode')
            accessors.XMLAttribute('lock_posix', self,
                                   parent_xpath='/',
                                   tag_name='lock',
                                   attribute='posix')
            accessors.XMLAttribute('flock', self,
                                   parent_xpath='/',
                                   tag_name='lock',
                                   attribute='flock')
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<binary/>'
