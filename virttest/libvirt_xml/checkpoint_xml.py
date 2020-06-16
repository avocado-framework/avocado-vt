"""
Module simplifying manipulation of XML described at
http://libvirt.org/formatdomaincheckpoint.html
"""
from virttest.libvirt_xml import base, accessors


class CheckpointXML(base.LibvirtXMLBase):
    """
    Domain checkpoint XML class

    Properties:
        name:
            string, name of the checkpoint
        description:
            string, description of the checkpoint
        disk:
            dict, key: name, checkpoint, bitmap.
            name: name of the disk,
            checkpoint (no/bitmap): whether to create checkpoint for the disk
            bitmap: name of the bitmap to be created
    """

    __slots__ = ('name', 'description', 'disks')

    __uncompareable__ = base.LibvirtXMLBase.__uncompareable__

    __schema_name__ = "domaincheckpoint"

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementText('name', self, parent_xpath='/',
                                 tag_name='name')
        accessors.XMLElementText('description', self, parent_xpath='/',
                                 tag_name='description')
        accessors.XMLElementList('disks', self, parent_xpath='/disks',
                                 marshal_from=self.marshal_from_disks,
                                 marshal_to=self.marshal_to_disks)
        super(self.__class__, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<domaincheckpoint><disks/></domaincheckpoint>'

    @staticmethod
    def marshal_from_disks(item, index, libvirtxml):
        """
        Convert a string to disk tag and attributes.
        """
        del index
        del libvirtxml
        return ('disk', dict(item))

    @staticmethod
    def marshal_to_disks(tag, attr_dict, index, libvirtxml):
        """
        Convert a disk tag and attributes to a string.
        """
        del index
        del libvirtxml
        if tag != 'disk':
            return None
        return dict(attr_dict)
