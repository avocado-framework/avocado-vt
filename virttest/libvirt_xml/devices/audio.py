"""
audio device support class(es)

https://libvirt.org/formatdomain.html#audio-devices
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Audio(base.UntypedDeviceBase):

    __slots__ = ('id', 'type', 'attrs', 'input_attrs',
                 'input_settings', 'output_attrs', 'output_settings')

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute('id', self,
                               parent_xpath='/',
                               tag_name='audio',
                               attribute='id')
        accessors.XMLAttribute('type', self,
                               parent_xpath='/',
                               tag_name='audio',
                               attribute='type')
        accessors.XMLElementDict('attrs', self,
                                 parent_xpath='/',
                                 tag_name='audio')
        accessors.XMLElementDict('input_attrs', self,
                                 parent_xpath='/',
                                 tag_name='input')
        accessors.XMLElementDict('input_settings', self,
                                 parent_xpath='/input',
                                 tag_name='settings')
        accessors.XMLElementDict('output_attrs', self,
                                 parent_xpath='/',
                                 tag_name='output')
        accessors.XMLElementDict('output_settings', self,
                                 parent_xpath='/output',
                                 tag_name='settings')
        super(Audio, self).__init__(device_tag='audio',
                                    virsh_instance=virsh_instance)
