"""
Virtualization test - network filter related utility functions
Module simplifying manipulation of XML described at
http://libvirt.org/formatnwfilter.html
"""

import logging

from virttest.libvirt_xml import base, accessors
from virttest.libvirt_xml.devices.interface import Filterref
from virttest import libvirt_xml

# network filter xml set up code BEGIN


def set_nwfilter_iface(New_iface,
                       type_name="network",
                       source={'network': "default"},
                       filterref_dict={}):
    """
    set iface to bind network or bind filter

    Params New_iface: instance of Interface,
    Params type_name: the type name which bind to interface
    Params source: source of new_iface, set as default
    Params filterref_dict: dict of network filter, which is not
    blank will bind to new_iface

    return:  new network interface
    """
    # set iface type name as network and binding source type
    New_iface.type_name = type_name
    New_iface.source = source
    # if filterref_dict is not blank , bind it to iface
    if filterref_dict:
        filterref = New_iface.new_filterref(**filterref_dict)
        New_iface.filterref = filterref
    # print the new iface xml
    logging.debug("new iface xml is: \n %s \n" % New_iface)
    return New_iface


def set_filterref_dict(filter_name, params, param_name, param_value):
    """
    set up the filter rule dict

    Params filter_name: string, network filter rule name.
    Params params: list of dict, the cfg file key and value.
    Params param_name: string, key of cfg file, param name of filter xml
    Params param_value: string, key of cfg file, param_value of filter xml

    return: filterref_dict: dict, can use to set up binding in interafce xml
    """
    filter_params_list = []
    params_key = [i for i in params.keys()
                  if param_name in i]
    params_value = [i for i in params.keys()
                    if param_value in i]
    params_key.sort()
    params_value.sort()
    for i in range(len(params_key)):
        params_dict = {}
        params_dict['name'] = params[params_key[i]]
        params_dict['value'] = params[params_value[i]]
        filter_params_list.append(params_dict)
    filterref_dict = {}
    filterref_dict['name'] = filter_name
    filterref_dict['parameters'] = filter_params_list
    return filterref_dict


# filter set up code
# END

# BEGIN
# Nwfilter binding file xml code


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
        Return a new interafce filterref instance from dargs
        """
        new_one = Filterref(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    def new_owner(self, name, uuid):
        """
        Return a new interafce Owner instance from name and uuid
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


def create_filterbinding_xml(vm_name,
                             mac_address='',
                             portdev='',
                             filterref_dict={}):
    """
    create nwfilter binding xml

    Params vm_name: string, name of vm
    Params mac_address: string, mac address of vm
    Params portdev: string, port dev of vm binding
    Params filterref_dict: dict, network filter  dict

    return: return xml instance, can binding filter to network interface
    """
    vmxml = libvirt_xml.VMXML.new_from_inactive_dumpxml(vm_name)
    binding = NwfilterBinding()
    binding.owner = binding.new_owner(vm_name, vmxml.uuid)
    binding.mac_address = mac_address
    binding.portdev = portdev
    binding.filterref = binding.new_filterref(**filterref_dict)
    logging.debug("filter binding xml is: %s" % binding)
    return binding

# Nwfilter binding code
# END
