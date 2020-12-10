"""
random number generator device support class(es)

http://libvirt.org/formatdomain.html#elementsRng
"""

from virttest.libvirt_xml import accessors, xcepts
from virttest.libvirt_xml.devices import base, librarian


class Rng(base.UntypedDeviceBase):

    __slots__ = ('rng_model', 'rate', 'backend', 'alias', 'address', 'driver')

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute('rng_model', self,
                               parent_xpath='/',
                               tag_name='rng',
                               attribute='model')
        accessors.XMLElementDict('rate', self,
                                 parent_xpath='/',
                                 tag_name='rate')
        accessors.XMLElementNest('backend', self, parent_xpath='/',
                                 tag_name='backend', subclass=self.Backend,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest('address', self, parent_xpath='/',
                                 tag_name='address', subclass=self.Address,
                                 subclass_dargs={'type_name': 'pci',
                                                 'virsh_instance': virsh_instance})
        accessors.XMLElementDict('alias', self, parent_xpath='/',
                                 tag_name='alias')
        accessors.XMLElementDict('driver', self, parent_xpath='/',
                                 tag_name='driver')
        super(Rng, self).__init__(
            device_tag='rng', virsh_instance=virsh_instance)
        self.xml = '<rng/>'

    Address = librarian.get('address')

    def new_rng_address(self, **dargs):
        """
        Return a new interface Address instance and set properties from dargs
        """
        new_one = self.Address("pci", virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    class Backend(base.base.LibvirtXMLBase):

        """
        Rng backend xml class.

        Properties:

        model:
            string. backend model
        type:
            string. backend type
        """
        __slots__ = ('backend_model', 'backend_type', 'backend_dev',
                     'source', 'backend_protocol')

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLAttribute(property_name="backend_model",
                                   libvirtxml=self,
                                   forbidden=None,
                                   parent_xpath='/',
                                   tag_name='backend',
                                   attribute='model')
            accessors.XMLAttribute(property_name="backend_type",
                                   libvirtxml=self,
                                   forbidden=None,
                                   parent_xpath='/',
                                   tag_name='backend',
                                   attribute='type')
            accessors.XMLElementText('backend_dev',
                                     self, parent_xpath='/',
                                     tag_name='backend')

            accessors.XMLElementList(property_name='source',
                                     libvirtxml=self,
                                     parent_xpath='/',
                                     marshal_from=self.marshal_from_source,
                                     marshal_to=self.marshal_to_source)
            accessors.XMLAttribute(property_name="backend_protocol",
                                   libvirtxml=self,
                                   forbidden=None,
                                   parent_xpath='/',
                                   tag_name='protocol',
                                   attribute='type')
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<backend/>'

        @staticmethod
        def marshal_from_source(item, index, libvirtxml):
            """Convert a dictionary into a tag + attributes"""
            del index           # not used
            del libvirtxml      # not used
            if not isinstance(item, dict):
                raise xcepts.LibvirtXMLError("Expected a dictionary of host "
                                             "attributes, not a %s"
                                             % str(item))
            return ('source', dict(item))  # return copy of dict, not reference

        @staticmethod
        def marshal_to_source(tag, attr_dict, index, libvirtxml):
            """Convert a tag + attributes into a dictionary"""
            del index                    # not used
            del libvirtxml               # not used
            if tag != 'source':
                return None              # skip this one
            return dict(attr_dict)       # return copy of dict, not reference
