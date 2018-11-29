"""
Network filter support class

https://libvirt.org/formatnwfilter.html#nwfconceptsvars
"""

from virttest.libvirt_xml import accessors, xcepts
from virttest.libvirt_xml.devices import base


class Filterref(base.base.LibvirtXMLBase):
    """
    Interface filterref xml class.

    Properties:

    name:
    string. filter name
    parameters:
    list. parameters element dict list
    """
    __slots__ = ("name", "parameters")

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute(property_name="name",
                               libvirtxml=self,
                               forbidden=None,
                               parent_xpath='/',
                               tag_name='filterref',
                               attribute='filter')
        accessors.XMLElementList(property_name='parameters',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 marshal_from=self.marshal_from_parameter,
                                 marshal_to=self.marshal_to_parameter)
        super(self.__class__, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<filterref/>'

    @staticmethod
    def marshal_from_parameter(item, index, libvirtxml):
        """Convert a dictionary into a tag + attributes"""
        del index           # not used
        del libvirtxml      # not used
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of parameter "
                                         "attributes, not a %s"
                                         % str(item))
            # return copy of dict, not reference
        return ('parameter', dict(item))

    @staticmethod
    def marshal_to_parameter(tag, attr_dict, index, libvirtxml):
        """Convert a tag + attributes into a dictionary"""
        del index                    # not used
        del libvirtxml               # not used
        if tag != 'parameter':
            return None              # skip this one
        return dict(attr_dict)       # return copy of dict, not reference@
