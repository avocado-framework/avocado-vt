"""
Module simplifying manipulation of XML described at
http://libvirt.org/formatnwfilter.html
"""

from virttest.libvirt_xml import base, accessors
from virttest.libvirt_xml.devices.filterref import Filterref


class NwfilterBinding(base.LibvirtXMLBase):
    """
    Accessor methods for NwfilterXML class
    simple example:

    <filterbinding>
    <owner>
    <name>rhel</name>
    <uuid>c9543ff4-1703-40a9-abbf-7f3e0fcd66c0</uuid>
    </owner>
    <portdev name='vnet0'/>
    <mac address='52:54:00:fa:81:87'/>
    <filterref filter='clean-traffic'>
    <parameter name='MAC' value='52:54:00:fa:81:87'/>
    </filterref>
    </filterbinding>


    Properties:
        owner:
        uuid: string,  domain uuid of vm
        portdev: port device of host
        mac_address: mac of the vnet0
        filterref:  list, list of dictionaries describing filterref properties
    """

    __slots__ = base.LibvirtXMLBase.__slots__ + ('owner', 'portdev',
                                                 'mac_address', 'filterref',)

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementNest("owner", self,
                                 parent_xpath='/',
                                 tag_name='owner',
                                 subclass=self.Owner,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLAttribute('portdev', self,
                               parent_xpath='/',
                               tag_name='portdev',
                               attribute='name')
        accessors.XMLAttribute('mac_address', self,
                               parent_xpath='/',
                               tag_name='mac',
                               attribute='address')
        accessors.XMLElementNest("filterref", self,
                                 parent_xpath='/',
                                 tag_name='filterref',
                                 subclass=Filterref,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        super(NwfilterBinding, self).__init__(virsh_instance=virsh_instance)

        self.xml = u'<filterbinding></filterbinding>'

    def new_filterref(self, **dargs):
        """
        Return a new interface filterref instance from dargs
        """
        new_one = Filterref(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_owner(self, name, uuid):
        """
        Return a new interface Owner instance from name and uuid
        """
        new_one = self.Owner(virsh_instance=self.virsh)
        new_one.name = name
        new_one.uuid = uuid
        return new_one

    class Owner(base.LibvirtXMLBase):
        """
        Interface Owner xml class

        Properties:
        name: string, name of the vm
        uuid: string, domain uuid of vm
        """
        __slots__ = ("name", "uuid")

        def __init__(self, virsh_instance=base.virsh):
            accessors.XMLElementText('name', self,
                                     parent_xpath='/',
                                     tag_name='name')
            accessors.XMLElementText('uuid', self,
                                     parent_xpath='/',
                                     tag_name='uuid')
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = u'<owner></owner>'
