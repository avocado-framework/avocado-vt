"""
tpm device support class(es)

http://libvirt.org/formatdomain.html#elementsTpm
"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base


class Tpm(base.UntypedDeviceBase):

    __slots__ = ('tpm_model', 'backend')

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute('tpm_model', self,
                               parent_xpath='/',
                               tag_name='tpm',
                               attribute='model')
        accessors.XMLElementNest('backend', self, parent_xpath='/',
                                 tag_name='backend', subclass=self.Backend,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        super(Tpm, self).__init__(
            device_tag='tpm', virsh_instance=virsh_instance)

    class Backend(base.base.LibvirtXMLBase):

        """
        Tpm backend xml class.

        Properties:

        type:
            string. backend type
        version:
            string. backend version
        persistent_state:
            string. backend persistent_state
        path:
            string. device path
        secret:
            string. encryption secret
        """
        __slots__ = ('backend_type', 'backend_version', 'persistent_state', 'device_path', 'encryption_secret')

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLAttribute(property_name="backend_type",
                                   libvirtxml=self,
                                   parent_xpath='/',
                                   tag_name='backend',
                                   attribute='type')
            accessors.XMLAttribute(property_name="backend_version",
                                   libvirtxml=self,
                                   parent_xpath='/',
                                   tag_name='backend',
                                   attribute='version')
            accessors.XMLAttribute(property_name="persistent_state",
                                   libvirtxml=self,
                                   parent_xpath='/',
                                   tag_name='backend',
                                   attribute='persistent_state')
            accessors.XMLAttribute(property_name="device_path",
                                   libvirtxml=self,
                                   parent_xpath='/',
                                   tag_name='device',
                                   attribute='path')
            accessors.XMLAttribute(property_name="encryption_secret",
                                   libvirtxml=self,
                                   parent_xpath='/',
                                   tag_name='encryption',
                                   attribute='secret')
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<backend/>'
