"""
Filter out certain devices from redirection
  <redirfilter>
    <usbdev class='0x08' vendor='0x1234' product='0xbeef' version='2.56' allow='yes'/>
    <usbdev allow='no'/>
  </redirfilter
https://libvirt.org/formatdomain.html#redirected-devices
"""

from virttest.libvirt_xml import accessors, xcepts
from virttest.libvirt_xml.devices import base


class Redirfilter(base.base.LibvirtXMLBase):
    """
    Interface redirfilter xml class.

    Properties:
    usbdev:
    list. usbdev element dict list
    """
    __slots__ = ("usbdevs", )

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLElementList(property_name='usbdevs',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 marshal_from=self.marshal_from_usbdev,
                                 marshal_to=self.marshal_to_usbdev)
        super(Redirfilter, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<redirfilter/>'

    @staticmethod
    def marshal_from_usbdev(item, index, libvirtxml):
        """Convert a dictionary into a tag + attributes"""
        del index           # not used
        del libvirtxml      # not used
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of parameter "
                                         "attributes, not a %s"
                                         % str(item))
            # return copy of dict, not reference
        return ('usbdev', dict(item))

    @staticmethod
    def marshal_to_usbdev(tag, attr_dict, index, libvirtxml):
        """Convert a tag + attributes into a dictionary"""
        del index                    # not used
        del libvirtxml               # not used
        if tag != 'usbdev':
            return None              # skip this one
        return dict(attr_dict)       # return copy of dict, not reference@
