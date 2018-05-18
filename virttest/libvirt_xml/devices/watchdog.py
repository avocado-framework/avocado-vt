"""
watchdog device support class(es)

http://libvirt.org/formatdomain.html#elementsWatchdog
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Watchdog(base.UntypedDeviceBase):

    __slots__ = ('model_type', 'action', 'address', 'alias')

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute('model_type', self,
                               parent_xpath='/',
                               tag_name='watchdog',
                               attribute='model')
        accessors.XMLAttribute('action', self,
                               parent_xpath='/',
                               tag_name='watchdog',
                               attribute='action')
        accessors.XMLElementDict('address', self,
                                 parent_xpath='/',
                                 tag_name='address')
        accessors.XMLElementDict('alias', self,
                                 parent_xpath='/',
                                 tag_name='alias')
        super(Watchdog, self).__init__(device_tag='watchdog',
                                       virsh_instance=virsh_instance)
