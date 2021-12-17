"""
watchdog device support class(es)

http://libvirt.org/formatdomain.html#elementsWatchdog
"""

import aexpect

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

    def try_modprobe(self, session):
        """
        Tries to load watchdog kernel module

        :param session: guest session
        :return: False if module can't be loaded
        """
        handled_types = {"ib700": "ib700wdt", "diag288": "diag288_wdt"}
        if self.model_type not in handled_types.keys():
            return False
        module = handled_types.get(self.model_type)
        try:
            session.cmd("modprobe %s" % module)
        except aexpect.ShellCmdError:
            session.close()
            return False
        return True
