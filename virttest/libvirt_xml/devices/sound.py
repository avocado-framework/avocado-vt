"""
sound device support class(es)

http://libvirt.org/formatdomain.html#elementsSound
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Sound(base.UntypedDeviceBase):

    __slots__ = ('model_type', 'codec_type', 'address')

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute('model_type', self,
                               parent_xpath='/',
                               tag_name='sound',
                               attribute='model')
        accessors.XMLAttribute('codec_type', self,
                               parent_xpath='/',
                               tag_name='codec',
                               attribute='type')
        accessors.XMLElementDict('address', self,
                                 parent_xpath='/',
                                 tag_name='address')
        super(Sound, self).__init__(device_tag='sound',
                                    virsh_instance=virsh_instance)
