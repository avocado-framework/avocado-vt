"""
Module simplifying manipulation of XML described at
http://libvirt.org/formatnetwork.html
"""

import logging
import six

from virttest import xml_utils
from virttest.libvirt_xml import base, xcepts, accessors
from virttest.libvirt_xml.devices import librarian


class RangeList(list):

    """
    A list of start & end address tuples
    """

    def __init__(self, iterable=None):
        """
        Initialize from list/tuple of two-item tuple start/end address strings
        """
        x_str = "iterable must contain two-item tuples of start/end addresses"
        newone = []
        for item in iterable:
            if not issubclass(type(item), tuple):
                raise xcepts.LibvirtXMLError(x_str)
            if len(item) != 2:
                raise xcepts.LibvirtXMLError(x_str)
            # Assume strings will be validated elsewhere
            newone.append(tuple(item))
        super(RangeList, self).__init__(newone)

    def append_to_element(self, element):
        """
        Adds range described by instance to ElementTree.element
        """
        if not issubclass(type(element), xml_utils.ElementTree.Element):
            raise ValueError(
                "Element is not a ElementTree.Element or subclass")
        for start, end in self:
            serange = {'start': start, 'end': end}
            element.append(xml_utils.ElementTree.Element('range', serange))


class IPXML(base.LibvirtXMLBase):

    """
    IP address block, optionally containing DHCP range information

    Properties:
        dhcp_ranges: Dict. keys: start, end
        host_attr: host mac, name and ip information
        address: string IP address
        netmask: string IP's netmask
    """

    __slots__ = ('dhcp_ranges', 'address', 'netmask', 'hosts',
                 'family', 'prefix', 'tftp_root', 'dhcp_bootp')

    def __init__(self, address='192.168.122.1', netmask='255.255.255.0',
                 ipv6=False, virsh_instance=base.virsh):
        """
        Create new IPXML instance based on address/mask
        """
        accessors.XMLAttribute(
            'address', self, parent_xpath='/', tag_name='ip',
            attribute='address')
        accessors.XMLAttribute(
            'netmask', self, parent_xpath='/', tag_name='ip',
            attribute='netmask')
        accessors.XMLAttribute(
            'family', self, parent_xpath='/', tag_name='ip',
            attribute='family')
        accessors.XMLAttribute(
            'prefix', self, parent_xpath='/', tag_name='ip',
            attribute='prefix')
        accessors.XMLAttribute(
            'tftp_root', self, parent_xpath='/', tag_name='tftp',
            attribute='root')
        accessors.XMLAttribute(
            'dhcp_bootp', self, parent_xpath='/dhcp', tag_name='bootp',
            attribute='file')
        accessors.XMLElementDict('dhcp_ranges', self,
                                 parent_xpath='/dhcp',
                                 tag_name='range')
        accessors.XMLElementList('hosts', self, parent_xpath='/dhcp',
                                 marshal_from=self.marshal_from_host,
                                 marshal_to=self.marshal_to_host)
        super(IPXML, self).__init__(virsh_instance=virsh_instance)
        if ipv6:
            self.xml = u"<ip address='%s'></ip>" % address
        else:
            self.xml = u"<ip address='%s' netmask='%s'></ip>" % (address, netmask)

    @staticmethod
    def marshal_from_host(item, index, libvirtxml):
        """Convert a dictionary into a tag + attributes"""
        del index           # not used
        del libvirtxml      # not used
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of host "
                                         "attributes, not a %s"
                                         % str(item))
        return ('host', dict(item))  # return copy of dict, not reference

    @staticmethod
    def marshal_to_host(tag, attr_dict, index, libvirtxml):
        """Convert a tag + attributes into a dictionary"""
        del index                    # not used
        del libvirtxml               # not used
        if tag != 'host':
            return None              # skip this one
        return dict(attr_dict)       # return copy of dict, not reference


class DNSXML(base.LibvirtXMLBase):

    """
    IP address block, optionally containing DHCP range information

    Properties:
        txt:
            Dict. keys: name, value
        forwarder:
            List
        srv:
            Dict. keys: service, protocol, domain,
            tartget, port, priority, weight
        hosts:
            List of host name
    """

    __slots__ = ('dns_forward', 'txt', 'forwarders', 'srv',
                 'host')

    def __init__(self, virsh_instance=base.virsh):
        """
        Create new IPXML instance based on address/mask
        """
        accessors.XMLElementDict('txt', self,
                                 parent_xpath='/',
                                 tag_name='txt')
        accessors.XMLElementDict('srv', self,
                                 parent_xpath='/',
                                 tag_name='srv')
        accessors.XMLElementList('forwarders', self, parent_xpath='/',
                                 marshal_from=self.marshal_from_forwarder,
                                 marshal_to=self.marshal_to_forwarder)
        accessors.XMLAttribute('dns_forward', self, parent_xpath='/',
                               tag_name='dns', attribute='forwardPlainNames')
        accessors.XMLElementNest('host', self, parent_xpath='/',
                                 tag_name='host', subclass=DNSXML.HostXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        super(DNSXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = u"<dns></dns>"

    class HostnameXML(base.LibvirtXMLBase):

        """
        Hostname element of dns
        """

        __slots__ = ('hostname',)

        def __init__(self, virsh_instance=base.virsh):
            """
            Create new HostnameXML instance
            """
            accessors.XMLElementText('hostname', self, parent_xpath='/',
                                     tag_name='hostname')
            super(DNSXML.HostnameXML, self).__init__(
                virsh_instance=virsh_instance)
            self.xml = '<hostname/>'

    class HostXML(base.LibvirtXMLBase):

        """
        Hostname element of dns
        """

        __slots__ = ('host_ip', 'hostnames',)

        def __init__(self, virsh_instance=base.virsh):
            """
            Create new TimerXML instance
            """
            accessors.XMLAttribute('host_ip', self, parent_xpath='/',
                                   tag_name='host', attribute='ip')
            accessors.XMLElementList('hostnames', self, parent_xpath='/',
                                     marshal_from=self.marshal_from_hostname,
                                     marshal_to=self.marshal_to_hostname)
            super(DNSXML.HostXML, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<host/>'

        @staticmethod
        def marshal_from_hostname(item, index, libvirtxml):
            """Convert a HostnameXML instance into a tag + attributes"""
            del index           # not used
            del libvirtxml      # not used
            if isinstance(item, six.string_types):
                return ("hostname", {}, item)
            else:
                raise xcepts.LibvirtXMLError("Expected a str attributes,"
                                             " not a %s" % str(item))

        @staticmethod
        def marshal_to_hostname(tag, attr, index, libvirtxml, text):
            """Convert a tag + attributes into a HostnameXML instance"""
            del attr                     # not used
            del index                    # not used
            if tag != 'hostname':
                return None     # Don't convert this item
            newone = DNSXML.HostnameXML(virsh_instance=libvirtxml.virsh)
            newone.hostname = text
            return newone

    def new_host(self, **dargs):
        """
        Return a new disk IOTune instance and set properties from dargs
        """
        new_one = DNSXML.HostXML(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    @staticmethod
    def marshal_from_forwarder(item, index, libvirtxml):
        """Convert a dictionary into a tag + attributes"""
        del index           # not used
        del libvirtxml      # not used
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of host "
                                         "attributes, not a %s"
                                         % str(item))
        return ('forwarder', dict(item))  # return copy of dict, not reference

    @staticmethod
    def marshal_to_forwarder(tag, attr_dict, index, libvirtxml):
        """Convert a tag + attributes into a dictionary"""
        del index                    # not used
        del libvirtxml               # not used
        if tag != 'forwarder':
            return None              # skip this one
        return dict(attr_dict)       # return copy of dict, not reference


class PortgroupXML(base.LibvirtXMLBase):

    """
    Accessor methods for PortgroupXML class in NetworkXML.

    Properties:
        name:
            string, operates on 'name' attribute of portgroup tag
        default:
            string of yes or no, operates on 'default' attribute of
            portgroup tag
        virtualport_type:
            string, operates on 'type' attribute of virtualport tag in
            portgroup.
        bandwidth_inbound:
            dict, operates on inbound tag in bandwidth which is child
            of portgroup.
        bandwidth_outbound:
            dict, operates on outbound tag in bandwidth which is child
            of portgroup.
        vlan_tag:
            dict, operates on vlan tag of portgroup
    """

    __slots__ = ('name', 'default', 'virtualport_type',
                 'bandwidth_inbound', 'bandwidth_outbound',
                 'vlan_tag')

    def __init__(self, virsh_instance=base.virsh):
        """
        Create new PortgroupXML instance.
        """
        accessors.XMLAttribute('name', self, parent_xpath='/',
                               tag_name='portgroup', attribute='name')
        accessors.XMLAttribute('default', self, parent_xpath='/',
                               tag_name='portgroup', attribute='default')
        accessors.XMLAttribute('virtualport_type', self, parent_xpath='/',
                               tag_name='virtualport', attribute='type')
        accessors.XMLElementDict('bandwidth_inbound', self,
                                 parent_xpath='/bandwidth',
                                 tag_name='inbound')
        accessors.XMLElementDict('bandwidth_outbound', self,
                                 parent_xpath='/bandwidth',
                                 tag_name='outbound')
        accessors.XMLElementDict('vlan_tag', self,
                                 parent_xpath='/vlan',
                                 tag_name='tag')
        super(PortgroupXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = u"<portgroup></portgroup>"


class NetworkXMLBase(base.LibvirtXMLBase):

    """
    Accessor methods for NetworkXML class.

    Properties:
        name:
            string, operates on XML name tag
        uuid:
            string, operates on uuid tag
        mac:
            string, operates on address attribute of mac tag
        ip:
            string operate on ip/dhcp ranges as IPXML instances
        forward:
            dict, operates on forward tag
        forward_interface:
            list, operates on forward/interface tag
        nat_port:
            dict, operates on nat tag
        bridge:
            dict, operates on bridge attributes
        routes:
            list, operates on route tag.
        virtualport_type:
            string, operates on 'type' attribute of virtualport tag.
        bandwidth_inbound:
            dict, operates on inbound under bandwidth.
        bandwidth_outbound:
            dict, operates on outbound under bandwidth.
        portgroup:
            PortgroupXML instance to access portgroup tag.
        domain_name:
            string, operates on name attribute of domain tag
        dns:
            DNSXML instance to access dns tag.

        defined:
            virtual boolean, callout to virsh methods
        get:
            True if libvirt knows network name
        set:
            True defines network, False undefines to libvirt
        del:
            Undefines network to libvirt

        active:
            virtual boolean, callout to virsh methods
        get:
            True if network is active to libvirt
        set:
            True activates network, False deactivates to libvirt
        del:
            Deactivates network to libvirt

        autostart:
            virtual boolean, callout to virsh methods
        get:
            True if libvirt autostarts network with same name
        set:
            True to set autostart, False to unset to libvirt
        del:
            Unset autostart to libvirt

        persistent:
            virtual boolean, callout to virsh methods
        get:
            True if network was defined, False if only created.
        set:
            Same as defined property
        del:
            Same as defined property
    """

    __slots__ = ('name', 'uuid', 'bridge', 'defined', 'active',
                 'autostart', 'persistent', 'forward', 'mac', 'ip',
                 'bandwidth_inbound', 'bandwidth_outbound', 'portgroup',
                 'dns', 'domain_name', 'nat_port', 'forward_interface',
                 'routes', 'virtualport_type', 'vf_list', 'driver', 'pf',
                 'mtu', 'connection', 'port', 'nat_attrs')

    __uncompareable__ = base.LibvirtXMLBase.__uncompareable__ + (
        'defined', 'active',
        'autostart', 'persistent')

    __schema_name__ = "network"

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLAttribute('connection', self, parent_xpath='/',
                               tag_name='network', attribute='connections')
        accessors.XMLElementText('name', self, parent_xpath='/',
                                 tag_name='name')
        accessors.XMLElementText('uuid', self, parent_xpath='/',
                                 tag_name='uuid')
        accessors.XMLAttribute('mac', self, parent_xpath='/',
                               tag_name='mac', attribute='address')
        accessors.XMLElementDict('forward', self, parent_xpath='/',
                                 tag_name='forward')
        accessors.XMLElementList('forward_interface', self, parent_xpath='/forward',
                                 marshal_from=self.marshal_from_forward_iface,
                                 marshal_to=self.marshal_to_forward_iface)
        accessors.XMLElementDict('nat_attrs', self, parent_xpath='/forward',
                                 tag_name='nat')
        accessors.XMLElementList('vf_list', self,
                                 parent_xpath='/forward',
                                 marshal_from=self.marshal_from_address,
                                 marshal_to=self.marshal_to_address)
        accessors.XMLElementDict('driver', self, parent_xpath='/',
                                 tag_name='driver')
        accessors.XMLElementDict('pf', self, parent_xpath='/forward',
                                 tag_name='pf')
        accessors.XMLElementDict('nat_port', self, parent_xpath='/forward/nat',
                                 tag_name='port')
        accessors.XMLElementDict('bridge', self, parent_xpath='/',
                                 tag_name='bridge')
        accessors.XMLElementDict('bandwidth_inbound', self,
                                 parent_xpath='/bandwidth',
                                 tag_name='inbound')
        accessors.XMLElementDict('bandwidth_outbound', self,
                                 parent_xpath='/bandwidth',
                                 tag_name='outbound')
        accessors.XMLElementDict('port', self, parent_xpath='/',
                                 tag_name='port')
        accessors.XMLAttribute("mtu", self, parent_xpath='/',
                               tag_name='mtu',  attribute='size')
        accessors.XMLAttribute('domain_name', self, parent_xpath='/',
                               tag_name='domain', attribute='name')
        accessors.XMLElementNest('dns', self, parent_xpath='/',
                                 tag_name='dns', subclass=DNSXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementList('routes', self, parent_xpath='/',
                                 marshal_from=self.marshal_from_route,
                                 marshal_to=self.marshal_to_route)
        accessors.XMLAttribute('virtualport_type', self, parent_xpath='/',
                               tag_name='virtualport', attribute='type')
        super(NetworkXMLBase, self).__init__(virsh_instance=virsh_instance)

    Address = librarian.get('address')

    def new_vf_address(self, **dargs):
        """
        Return a new interface Address instance and set properties from dargs
        """
        new_one = self.Address("pci", virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    @staticmethod
    def marshal_from_address(item, index, libvirtxml):
        """Convert an Address instance into tag + attributes"""
        root = item.xmltreefile.getroot()
        if root.tag == 'address':
            return (root.tag, dict(list(root.items())))
        else:
            raise xcepts.LibvirtXMLError("Expected a list of address "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_address(self, tag, attr_dict, index, libvirtxml):
        """Convert a tag + attributes into an Address instance"""
        if not tag == 'address':
            return None
        newone = self.new_vf_address(attr_dict)
        return newone

    def __check_undefined__(self, errmsg):
        if not self.defined:
            raise xcepts.LibvirtXMLError(errmsg)

    def get_defined(self):
        """
        Accessor for 'define' property - does this name exist in network list
        """
        params = {'only_names': True, 'virsh_instance': self.virsh}
        return self.name in self.virsh.net_state_dict(**params)

    def set_defined(self, value):
        """Accessor method for 'define' property, set True to define."""
        if not self.__super_get__('INITIALIZED'):
            pass  # do nothing
        value = bool(value)
        if value:
            self.virsh.net_define(self.xml)  # send it the filename
        else:
            del self.defined

    def del_defined(self):
        """Accessor method for 'define' property, undefines network"""
        self.__check_undefined__("Cannot undefine non-existant network")
        self.virsh.net_undefine(self.name)

    def get_active(self):
        """Accessor method for 'active' property (True/False)"""
        state_dict = self.virsh.net_state_dict(virsh_instance=self.virsh)
        try:
            active_state = state_dict[self.name]['active']
        except KeyError:
            return False
        return active_state

    def set_active(self, value):
        """Accessor method for 'active' property, sets network active"""
        if not self.__super_get__('INITIALIZED'):
            pass  # do nothing
        self.__check_undefined__("Cannot activate undefined network")
        value = bool(value)
        if value:
            if not self.active:
                self.virsh.net_start(self.name)
            else:
                pass  # don't activate twice
        else:
            if self.active:
                del self.active
            else:
                pass  # don't deactivate twice

    def del_active(self):
        """Accessor method for 'active' property, stops network"""
        if self.active:
            self.virsh.net_destroy(self.name)
        else:
            pass  # don't destroy twice

    def get_autostart(self):
        """Accessor method for 'autostart' property, True if set"""
        self.__check_undefined__("Cannot determine autostart for undefined "
                                 "network")
        state_dict = self.virsh.net_state_dict(virsh_instance=self.virsh)
        return state_dict[self.name]['autostart']

    def set_autostart(self, value):
        """Accessor method for 'autostart' property, sets/unsets autostart"""
        if not self.__super_get__('INITIALIZED'):
            pass  # do nothing
        self.__check_undefined__("Cannot set autostart for undefined network")
        value = bool(value)
        if value:
            if not self.autostart:
                self.virsh.net_autostart(self.name)
            else:
                pass  # don't set autostart twice
        else:
            if self.autostart:
                del self.autostart
            else:
                pass  # don't unset autostart twice

    def del_autostart(self):
        """Accessor method for 'autostart' property, unsets autostart"""
        if not self.defined:
            raise xcepts.LibvirtXMLError("Can't autostart nonexistant network")
        self.virsh.net_autostart(self.name, "--disable")

    def get_persistent(self):
        """Accessor method for 'persistent' property"""
        state_dict = self.virsh.net_state_dict(virsh_instance=self.virsh)
        return state_dict[self.name]['persistent']

    # Copy behavior for consistency
    set_persistent = set_defined
    del_persistent = del_defined

    def get_ip(self):
        xmltreefile = self.__dict_get__('xml')
        try:
            ip_root = xmltreefile.reroot('/ip')
        except KeyError as detail:
            raise xcepts.LibvirtXMLError(detail)
        ipxml = IPXML(virsh_instance=self.__dict_get__('virsh'))
        ipxml.xmltreefile = ip_root
        return ipxml

    def set_ip(self, value):
        if not issubclass(type(value), IPXML):
            raise xcepts.LibvirtXMLError("value must be a IPXML or subclass")
        xmltreefile = self.__dict_get__('xml')
        # IPXML root element is whole IP element tree
        root = xmltreefile.getroot()
        root.append(value.xmltreefile.getroot())
        xmltreefile.write()

    def del_ip(self):
        xmltreefile = self.__dict_get__('xml')
        element = xmltreefile.find('/ip')
        if element is not None:
            xmltreefile.remove(element)
            xmltreefile.write()

    def del_element(self, element='', index=0):
        """
        Delete element from network xml

        :param element: xpath of element like '/ip/dhcp'
        :param index: index of element that want to delete
        """
        xmltreefile = self.__dict_get__('xml')
        try:
            del_elem = xmltreefile.findall(element)[index]
        except IndexError as detail:
            del_elem = None
            logging.warning(detail)
        if del_elem is not None:
            xmltreefile.remove(del_elem)
            xmltreefile.write()

    def get_portgroup(self):
        try:
            portgroup_root = self.xmltreefile.reroot('/portgroup')
        except KeyError as detail:
            raise xcepts.LibvirtXMLError(detail)
        portgroup_xml = PortgroupXML(virsh_instance=self.__dict_get__('virsh'))
        portgroup_xml.xmltreefile = portgroup_root
        return portgroup_xml

    def set_portgroup(self, value):
        if not issubclass(type(value), PortgroupXML):
            raise xcepts.LibvirtXMLError("value must be a PortgroupXML"
                                         "instance or subclass.")
        root = self.xmltreefile.getroot()
        root.append(value.xmltreefile.getroot())
        self.xmltreefile.write()

    def del_portgroup(self):
        element = self.xmltreefile.find("/portgroup")
        if element is not None:
            self.xmltreefile.remove(element)
            self.xmltreefile.write()

    def get_interface_connection(self):
        try:
            ifaces = self.xmltreefile.findall("/forward/interface")
        except KeyError as detail:
            raise xcepts.LibvirtXMLError(detail)
        iface_conn = []
        for iface in ifaces:
            try:
                iface_conn.append(iface.get("connections"))
            except KeyError:
                pass
        return iface_conn

    def new_dns(self, **dargs):
        """
        Return a new dns instance and set properties from dargs
        """
        new_one = DNSXML(virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    @staticmethod
    def marshal_from_forward_iface(item, index, libvirtxml):
        """Convert a dictionary into a tag + attributes"""
        del index           # not used
        del libvirtxml      # not used
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of interface "
                                         "attributes, not a %s"
                                         % str(item))
        return ('interface', dict(item))  # return copy of dict, not reference

    @staticmethod
    def marshal_to_forward_iface(tag, attr_dict, index, libvirtxml):
        """Convert a tag + attributes into a dictionary"""
        del index                    # not used
        del libvirtxml               # not used
        if tag != 'interface':
            return None              # skip this one
        return dict(attr_dict)       # return copy of dict, not reference

    @staticmethod
    def marshal_from_route(item, index, libvirtxml):
        """Convert a dictionary into a tag + attributes"""
        del index           # not used
        del libvirtxml      # not used
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of interface "
                                         "attributes, not a %s"
                                         % str(item))
        return ('route', dict(item))  # return copy of dict, not reference

    @staticmethod
    def marshal_to_route(tag, attr_dict, index, libvirtxml):
        """Convert a tag + attributes into a dictionary"""
        del index                    # not used
        del libvirtxml               # not used
        if tag != 'route':
            return None              # skip this one
        return dict(attr_dict)       # return copy of dict, not reference


class NetworkXML(NetworkXMLBase):

    """
    Manipulators of a Virtual Network through it's XML definition.
    """

    __slots__ = []

    def __init__(self, network_name='default', virsh_instance=base.virsh):
        """
        Initialize new instance with empty XML
        """
        super(NetworkXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = u"<network><name>%s</name></network>" % network_name

    @staticmethod  # wraps __new__
    def new_all_networks_dict(virsh_instance=base.virsh):
        """
        Return a dictionary of names to NetworkXML instances for all networks

        :param virsh: virsh module or instance to use
        :return: Dictionary of network name to NetworkXML instance
        """
        result = {}
        # Values should all share virsh property
        new_netxml = NetworkXML(virsh_instance=virsh_instance)
        params = {'only_names': True, 'virsh_instance': virsh_instance}
        networks = list(new_netxml.virsh.net_state_dict(**params).keys())
        for net_name in networks:
            new_copy = new_netxml.copy()
            dump_result = virsh_instance.net_dumpxml(net_name)
            new_copy.xml = dump_result.stdout_text.strip()
            result[net_name] = new_copy
        return result

    @staticmethod
    def new_from_net_dumpxml(network_name, virsh_instance=base.virsh, extra=""):
        """
        Return new NetworkXML instance from virsh net-dumpxml command

        :param network_name: Name of network to net-dumpxml
        :param virsh_instance: virsh module or instance to use
        :return: New initialized NetworkXML instance
        """
        netxml = NetworkXML(virsh_instance=virsh_instance)
        dump_result = virsh_instance.net_dumpxml(network_name, extra)
        netxml['xml'] = dump_result.stdout_text.strip()
        return netxml

    @staticmethod
    def get_uuid_by_name(network_name, virsh_instance=base.virsh):
        """
        Return Network's uuid by Network's name.

        :param network_name: Network's name
        :return: Network's uuid
        """
        network_xml = NetworkXML.new_from_net_dumpxml(network_name,
                                                      virsh_instance)
        return network_xml.uuid

    def debug_xml(self):
        """
        Dump contents of XML file for debugging
        """
        xml = str(self)  # LibvirtXMLBase.__str__ returns XML content
        for debug_line in str(xml).splitlines():
            logging.debug("Network XML: %s", debug_line)

    def state_dict(self):
        """
        Return a dict containing states of active/autostart/persistent

        :return: A dict contains active/autostart/persistent as keys
                 and boolean as values or None if network doesn't exist.
        """
        if self.defined:
            return self.virsh.net_state_dict(virsh_instance=self.virsh)[self.name]

    def create(self, **dargs):
        """
        Adds non-persistant / transient network to libvirt with net-create
        """
        cmd_result = self.virsh.net_create(self.xml, **dargs)
        if cmd_result.exit_status:
            raise xcepts.LibvirtXMLError("Failed to create transient network %s.\n"
                                         "Detail: %s" %
                                         (self.name, cmd_result.stderr))

    def orbital_nuclear_strike(self):
        """It's the only way to really be sure.  Remove all libvirt state"""
        try:
            self['active'] = False  # deactivate (stop) network if active
        except xcepts.LibvirtXMLError as detail:
            # inconsequential, network will be removed
            logging.warning(detail)
        try:
            self['defined'] = False  # undefine (delete) network if persistent
        except xcepts.LibvirtXMLError as detail:
            # network already gone
            logging.warning(detail)

    def exists(self):
        """
        Return True if network already exists.
        """
        cmd_result = self.virsh.net_uuid(self.name)
        return (cmd_result.exit_status == 0)

    def undefine(self):
        """
        Undefine network witch name is self.name.
        """
        self.virsh.net_destroy(self.name)
        cmd_result = self.virsh.net_undefine(self.name)
        if cmd_result.exit_status:
            raise xcepts.LibvirtXMLError("Failed to undefine network %s.\n"
                                         "Detail: %s" %
                                         (self.name,
                                          cmd_result.stderr_text))

    def define(self):
        """
        Define network from self.xml.
        """
        cmd_result = self.virsh.net_define(self.xml)
        if cmd_result.exit_status:
            raise xcepts.LibvirtXMLError("Failed to define network %s.\n"
                                         "Detail: %s" %
                                         (self.name,
                                          cmd_result.stderr_text))

    def start(self):
        """
        Start network with self.virsh.
        """
        cmd_result = self.virsh.net_start(self.name, debug=True)
        if cmd_result.exit_status:
            raise xcepts.LibvirtXMLError("Failed to start network %s.\n"
                                         "Detail: %s" %
                                         (self.name,
                                          cmd_result.stderr_text))

    def sync(self, state=None):
        """
        Make the change of "self" take effect on network.
        Recover network to designated state if option state is set.

        :param state: a boolean dict contains active/persistent/autostart as
                      keys
        """
        if self['defined']:
            if self['active']:
                del self['active']
            if self['defined']:
                del self['defined']

        self['defined'] = True
        if state:
            self['active'] = state['active']
            if not state['persistent']:
                del self['persistent']
            if self.defined:
                self['autostart'] = state['autostart']
        else:
            self['active'] = True
            self['autostart'] = True
