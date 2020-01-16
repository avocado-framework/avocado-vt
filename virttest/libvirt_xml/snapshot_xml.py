"""
Module simplifying manipulation of XML described at
http://libvirt.org/formatsnapshot.html
"""

from virttest import xml_utils
from virttest.libvirt_xml import base, accessors
from virttest.libvirt_xml.devices.disk import Disk
from virttest.libvirt_xml import xcepts


class SnapshotXMLBase(base.LibvirtXMLBase):

    """
    Accessor methods for SnapshotXML class.

    Properties:
        snap_name:
            string, operates on snapshot name tag
        description:
            string, operates on snapshot description tag
        mem_snap_type:
            string, operates snapshot type under memory tag, 'internal',
            'external' or 'no'
        mem_file:
            string, operates snapshot file path under memory tag
        creation_time:
            string, operates on creationTime tag
        state:
            string, operates snapshot state tag
        parent_name:
            string, parent snapshot name tag under parent tag
    """

    __slots__ = ('snap_name', 'description', 'mem_snap_type', 'mem_file',
                 'creation_time', 'state', 'parent_name')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementText('snap_name', self, parent_xpath='/',
                                 tag_name='name')
        accessors.XMLElementText('description', self, parent_xpath='/',
                                 tag_name='description')
        accessors.XMLAttribute('mem_snap_type', self, parent_xpath='/',
                               tag_name='memory', attribute='snapshot')
        accessors.XMLAttribute('mem_file', self, parent_xpath='/',
                               tag_name='memory', attribute='file')
        accessors.XMLElementText('creation_time', self, parent_xpath='/',
                                 tag_name='creationTime')
        accessors.XMLElementText('state', self, parent_xpath='/',
                                 tag_name='state')
        accessors.XMLElementText('parent_name', self, parent_xpath='/parent',
                                 tag_name='name')
        super(SnapshotXMLBase, self).__init__(virsh_instance=virsh_instance)


class SnapshotXML(SnapshotXMLBase):

    """
    Manipulators of a snapshot through it's XML definition.
    """

    __slots__ = []

    def __init__(self, virsh_instance=base.virsh):
        """
        Initialize new instance with empty XML
        """
        super(SnapshotXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = u"<domainsnapshot><disks>\
                     </disks></domainsnapshot>"

    @staticmethod
    def new_from_snapshot_dumpxml(name, snap_name, virsh_instance=base.virsh):
        """
        Return new SnapshotXML instance from virsh snapshot-dumpxml command

        :param name: vm's name
        :param snap_name: snapshot name
        :param uuid: snapshot's uuid
        :param virsh_instance: virsh module or instance to use
        :return: New initialized SnapshotXML instance
        """
        snapshot_xml = SnapshotXML(virsh_instance=virsh_instance)
        result = virsh_instance.snapshot_dumpxml(name, snap_name)
        snapshot_xml['xml'] = result.stdout_text.strip()

        return snapshot_xml

    def set_disks(self, value_list):
        """
        Define disks based on contents of SnapDiskXML instance list

        :param value_list: SnapDiskXML instance list
        """
        for value in value_list:
            value_type = type(value)
            if not isinstance(value, self.SnapDiskXML):
                raise xcepts.LibvirtXMLError("Value %s Must be a instance of "
                                             "SnapDiskXML, not a %s"
                                             % (str(value), str(value_type)))
        # Start with clean slate
        exist_dev = self.xmltreefile.find('disks')
        if exist_dev is not None:
            self.del_disks()
        if len(value_list) > 0:
            disks_element = xml_utils.ElementTree.SubElement(
                self.xmltreefile.getroot(), 'disks')
            for disk in value_list:
                # Separate the element from the tree
                disk_element = disk.xmltreefile.getroot()
                disks_element.append(disk_element)
        self.xmltreefile.write()

    def del_disks(self):
        """
        Remove all disks
        """
        self.xmltreefile.remove_by_xpath('/disks', remove_all=True)
        self.xmltreefile.write()

    class SnapDiskXML(Disk):

        """
        Manipulators disk xml in snapshot xml definition.
        Most properties are inherit from parent class Disk.

        Properties:
            disk_name:
                string, operates on disk name under disk tag
        """

        __slots__ = Disk.__slots__ + ('disk_name', )

        def __init__(self, virsh_instance=base.virsh):
            """
            Initialize new instance with empty XML
            """
            accessors.XMLAttribute('disk_name', self, parent_xpath='/',
                                   tag_name='disk', attribute='name')
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = u"<disk></disk>"
