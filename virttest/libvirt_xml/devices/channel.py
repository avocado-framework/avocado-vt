"""
Classes to support XML for channel devices

http://libvirt.org/formatdomain.html#elementCharSerial
"""

from virttest.libvirt_xml import base
from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices.character import CharacterBase


class Channel(CharacterBase):

    __slots__ = ('source', 'target', 'alias', 'address')

    def __init__(self, type_name='unix', virsh_instance=base.virsh):
        accessors.XMLElementDict('source', self, parent_xpath='/',
                                 tag_name='source')
        accessors.XMLElementDict('target', self, parent_xpath='/',
                                 tag_name='target')
        # example for new slots :  alias and address
        #
        # <?xml version='1.0' encoding='UTF-8'?>
        # <channel type="pty">
        #   <source path="/dev/pts/10" />
        #   <target name="pty" type="virtio" />
        #   <alias name="pty" />
        #   <address bus="0" controller="0" type="virtio-serial" />
        # </channel>
        accessors.XMLElementDict('alias', self, parent_xpath='/',
                                 tag_name='alias')
        accessors.XMLElementDict('address', self, parent_xpath='/',
                                 tag_name='address')
        super(
            Channel, self).__init__(device_tag='channel', type_name=type_name,
                                    virsh_instance=virsh_instance)
