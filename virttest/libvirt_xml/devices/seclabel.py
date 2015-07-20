"""
seclabel device support class(es)

http://libvirt.org/formatdomain.html#seclabel
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Seclabel(base.TypedDeviceBase):

    """
    Seclabel XML class

    Properties:
        model:
            string, security driver model
        relabel:
            string, 'yes' or 'no'
        baselabel:
            string, base label string
        label:
            string, the sec label string
    """

    __slots__ = ('model', 'relabel', 'baselabel', 'label')

    def __init__(self, type_name='dynamic', virsh_instance=base.base.virsh):
        accessors.XMLAttribute('model', self, parent_xpath='/',
                               tag_name='seclabel', attribute='model')
        accessors.XMLAttribute('relabel', self, parent_xpath='/',
                               tag_name='seclabel', attribute='relabel')
        accessors.XMLElementText('baselabel', self, parent_xpath='/',
                                 tag_name='baselabel')
        accessors.XMLElementText('label', self, parent_xpath='/',
                                 tag_name='label')
        super(Seclabel, self).__init__(device_tag='seclabel',
                                       type_name=type_name,
                                       virsh_instance=virsh_instance)
        self.xml = '<seclabel></seclabel>'
