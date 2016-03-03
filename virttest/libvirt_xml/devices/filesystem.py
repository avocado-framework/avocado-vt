"""
filesystem device support class(es)

http://libvirt.org/formatdomain.html#elementsFilesystems
"""

from virttest.libvirt_xml.devices import base
from virttest.libvirt_xml import accessors


class Filesystem(base.TypedDeviceBase):

    __slots__ = ('accessmode', 'source', 'target')

    def __init__(self, type_name='mount', virsh_instance=base.base.virsh):
        accessors.XMLAttribute('accessmode', self, parent_xpath='/',
                               tag_name='filesystem', attribute='accessmode')
        accessors.XMLElementDict('source', self, parent_xpath='/',
                                 tag_name='source')
        accessors.XMLElementDict('target', self, parent_xpath='/',
                                 tag_name='target')
        super(Filesystem, self).__init__(device_tag='filesystem',
                                         type_name=type_name,
                                         virsh_instance=virsh_instance)
