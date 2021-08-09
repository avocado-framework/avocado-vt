"""
Module simplifying manipulation of XML described at
http://libvirt.org/formatcaps.html
"""

from virttest import xml_utils
from virttest.libvirt_xml import base, accessors, xcepts


class CapabilityXML(base.LibvirtXMLBase):

    """
    Handler of libvirt capabilities and nonspecific item operations.

    Properties:
        uuid:
            string of host uuid
        guest_capabilities:
            dict, read-only
        get:
            dict map from os type names to dict map from arch names
    """

    # TODO: Add more __slots__ and accessors to get some useful stats
    # e.g. guest_count etc.

    __slots__ = ('uuid', 'guest_capabilities', 'cpu_count', 'arch', 'model',
                 'vendor', 'feature_list', 'power_management_list',
                 'cpu_topology', 'cells_topology', 'iommu')
    __schema_name__ = "capability"

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementText(property_name="uuid",
                                 libvirtxml=self,
                                 forbidden=['set', 'del'],
                                 parent_xpath='/host',
                                 tag_name='uuid')
        # This will skip self.get_guest_capabilities() defined below
        accessors.AllForbidden(property_name="guest_capabilities",
                               libvirtxml=self)
        # This will skip self.get_cpu_count() defined below
        accessors.AllForbidden(property_name="cpu_count",
                               libvirtxml=self)
        # The set action is for test.
        accessors.XMLElementText(property_name="arch",
                                 libvirtxml=self,
                                 forbidden=['del'],
                                 parent_xpath='/host/cpu',
                                 tag_name='arch')
        accessors.XMLElementText(property_name="model",
                                 libvirtxml=self,
                                 forbidden=['del'],
                                 parent_xpath='/host/cpu',
                                 tag_name='model')
        accessors.XMLElementText(property_name="vendor",
                                 libvirtxml=self,
                                 forbidden=['del'],
                                 parent_xpath='/host/cpu',
                                 tag_name='vendor')
        accessors.XMLElementDict(property_name="cpu_topology",
                                 libvirtxml=self,
                                 forbidden=['del'],
                                 parent_xpath='/host/cpu',
                                 tag_name='topology')
        accessors.XMLElementDict(property_name="iommu",
                                 libvirtxml=self,
                                 forbidden=['del'],
                                 parent_xpath='/host',
                                 tag_name='iommu')
        accessors.XMLElementNest(property_name='cells_topology',
                                 libvirtxml=self,
                                 parent_xpath='/host',
                                 tag_name='topology',
                                 subclass=TopologyXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        # This will skip self.get_feature_list() defined below
        accessors.AllForbidden(property_name="feature_list",
                               libvirtxml=self)
        # This will skip self.get_power_management_list() defined below
        accessors.AllForbidden(property_name="power_management_list",
                               libvirtxml=self)
        super(CapabilityXML, self).__init__(virsh_instance)
        # calls set_xml accessor method
        self['xml'] = self.__dict_get__('virsh').capabilities()

    def get_guest_capabilities(self):
        """
        Accessor method for guest_capabilities property (in __slots__).
        Return a guest capabilities dict in following schema:
        {<os_type>: {<arch name>: {'wordsize': '', 'emulator': '',
        'machine': [<machine name>, ...], 'domaini_<type>': {'emulator': ''}}}}
        """
        guest_capa = {}
        xmltreefile = self.__dict_get__('xml')
        for guest in xmltreefile.findall('guest'):
            os_type_name = guest.find('os_type').text
            # Multiple guest definitions can share same os_type (e.g. hvm, pvm)
            if os_type_name == 'xen':
                os_type_name = 'pv'
            guest_arch = guest_capa.get(os_type_name, {})
            for arch in guest.findall('arch'):
                arch_name = arch.get('name')
                arch_prop = guest_arch.get(arch_name, {})
                arch_prop['wordsize'] = arch.find('wordsize').text
                arch_prop['emulator'] = arch.find('emulator').text
                # TODO: maxcpus differs for machine in a given arch.
                # Right now takes first machine as default for the given
                # arch and assigns maxcpu for the arch, ideally below machine
                # list to get populated with maxcpu for each machine
                # not modifying as no requirement for now and as it would break
                # other places where machine list is used.
                arch_prop['maxcpus'] = arch.findall('machine')[0].get('maxCpus')
                m_list = []
                for machine in arch.findall('machine'):
                    machine_text = machine.text
                    # Don't add duplicate entries
                    if not m_list.count(machine_text):
                        m_list.append(machine_text)
                arch_prop['machine'] = m_list
                for domain in arch.findall('domain'):
                    domain_name = "domain_" + domain.get('type')
                    dom_prop = {}
                    if domain.find('emulator') is not None:
                        dom_prop['emulator'] = domain.find('emulator').text
                    arch_prop[domain_name] = dom_prop
                guest_arch[arch_name] = arch_prop
            guest_capa[os_type_name] = guest_arch
        return guest_capa

    def get_power_management_list(self):
        """
        Accessor method for power_management_list property (in __slots__)
        """
        xmltreefile = self.__dict_get__('xml')
        pms = xmltreefile.find('host').find('power_management').getchildren()
        return [pm.tag for pm in pms]

    def get_feature_list(self):
        """
        Accessor method for feature_list property (in __slots__)
        """
        feature_list = []  # [<feature1>, <feature2>, ...]
        xmltreefile = self.__dict_get__('xml')
        for feature_node in xmltreefile.findall('/host/cpu/feature'):
            feature_list.append(feature_node)
        return feature_list

    def get_feature(self, num):
        """
        Get a feature element from feature list by number

        :return: Feature element
        """
        count = len(self.feature_list)
        try:
            num = int(num)
            return self.feature_list[num]
        except (ValueError, TypeError):
            raise xcepts.LibvirtXMLError("Invalid feature number %s" % num)
        except IndexError:
            raise xcepts.LibvirtXMLError("Only %d feature(s)" % count)

    def get_feature_name(self, num):
        """
        Get assigned feature name

        :param num: Assigned feature number
        :return: Assigned feature name
        """
        return self.get_feature(num).get('name')

    def get_cpu_count(self):
        """
        Accessor method for cpu_count property (in __slots__)
        """
        cpu_count = 0
        xmltreefile = self.__dict_get__('xml')
        for cpus in xmltreefile.findall('/host/topology/cells/cell/cpus'):
            cpu_num = cpus.get('num')
            cpu_count += int(cpu_num)
        return cpu_count

    def remove_feature(self, num):
        """
        Remove a assigned feature from xml

        :param num: Assigned feature number
        """
        xmltreefile = self.__dict_get__('xml')
        feature_remove_node = self.get_feature(num)
        cpu_node = xmltreefile.find('/host/cpu')
        cpu_node.remove(feature_remove_node)

    def check_feature_name(self, name):
        """
        Check feature name valid or not.

        :param name: The checked feature name
        :return: True if check pass
        """
        sys_feature = []
        cpu_xml_file = open('/proc/cpuinfo', 'r')
        for line in cpu_xml_file.readlines():
            if line.find('flags') != -1:
                feature_names = line.split(':')[1].strip()
                sys_sub_feature = feature_names.split(' ')
                sys_feature = list(set(sys_feature + sys_sub_feature))
        cpu_xml_file.close()
        return (name in sys_feature)

    def set_feature(self, num, value):
        """
        Set a assigned feature value to xml

        :param num: Assigned feature number
        :param value: The feature name modified to
        """
        feature_set_node = self.get_feature(num)
        feature_set_node.set('name', value)

    def add_feature(self, value):
        """
        Add a feature Element to xml

        :param value: The added feature name
        """
        xmltreefile = self.__dict_get__('xml')
        cpu_node = xmltreefile.find('/host/cpu')
        xml_utils.ElementTree.SubElement(cpu_node, 'feature', {'name': value})


class TopologyXML(base.LibvirtXMLBase):

    """
    Handler of cells topology element in libvirt capabilities.

    Properties:
        num:
            string of node cell numbers
        cell:
            list of cpu dict
    """

    __slots__ = ('num', 'cell')

    def __init__(self, virsh_instance=base.virsh):
        """
        Create new cells topology XML instance
        """
        accessors.XMLAttribute(property_name="num",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='cells',
                               attribute='num')
        accessors.AllForbidden(property_name="cell",
                               libvirtxml=self)
        super(TopologyXML, self).__init__(virsh_instance)
        self.xml = self.__dict_get__('virsh').capabilities()
        self.xmltreefile.reroot("/host/topology")
        self.xmltreefile.write()

    def get_cell(self, withmem=False):
        """
        Return CellXML instances list
        """
        cell_list = []
        for cell_node in self.xmltreefile.findall('/cells/cell'):
            if not cell_node.find('memory') and withmem:
                continue
            xml_str = xml_utils.ElementTree.tostring(
                cell_node)
            new_cell = CellXML()
            new_cell.xml = xml_str
            cell_list.append(new_cell)
        return cell_list


class CellXML(base.LibvirtXMLBase):

    """
    Handler of cell element in libvirt capabilities.

    Properties:
        cell_id:
            string of node cell number id
        memory:
            int, memory size
        mem_unit:
            string of memory unit
        pages:
            list of pages dict
        sibling:
            list of sibling dict
        cpus_num:
            string of cpus number
        cpu:
            list of cpu dict
    """

    __slots__ = ('cell_id', 'memory', 'mem_unit', 'pages', 'sibling',
                 'cpus_num', 'cpu')

    def __init__(self, virsh_instance=base.virsh):
        """
        Create new cpus XML instance
        """
        accessors.XMLAttribute(property_name="cell_id",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='cell',
                               attribute='id')
        accessors.XMLElementInt(property_name="memory",
                                libvirtxml=self,
                                parent_xpath='/',
                                tag_name='memory')
        accessors.XMLAttribute(property_name="mem_unit",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='memory',
                               attribute='unit')
        accessors.XMLElementList(property_name="pages",
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 marshal_from=self.marshal_from_pages,
                                 marshal_to=self.marshal_to_pages)
        accessors.XMLElementList(property_name="sibling",
                                 libvirtxml=self,
                                 parent_xpath='/distances',
                                 marshal_from=self.marshal_from_sibling,
                                 marshal_to=self.marshal_to_sibling)
        accessors.XMLAttribute(property_name="cpus_num",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='cpus',
                               attribute='num')
        accessors.XMLElementList(property_name="cpu",
                                 libvirtxml=self,
                                 parent_xpath='/cpus',
                                 marshal_from=self.marshal_from_cpu,
                                 marshal_to=self.marshal_to_cpu)
        super(CellXML, self).__init__(virsh_instance)
        self.xml = u"<cell></cell>"

    @staticmethod
    def marshal_from_pages(item, index, libvirtxml):
        """
        Convert a dict to pages tag and attributes.
        """
        del index
        del libvirtxml
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of pages "
                                         "attributes, not a %s"
                                         % str(item))
        return ('pages', dict(item))

    @staticmethod
    def marshal_to_pages(tag, attr_dict, index, libvirtxml, text):
        """
        Convert a pages tag and attributes to a dict.
        """
        del index
        del libvirtxml
        if tag != 'pages':
            return None
        attr_dict['text'] = text
        return dict(attr_dict)

    @staticmethod
    def marshal_from_sibling(item, index, libvirtxml):
        """
        Convert a dict to sibling tag and attributes.
        """
        del index
        del libvirtxml
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of sibling "
                                         "attributes, not a %s"
                                         % str(item))
        return ('sibling', dict(item))

    @staticmethod
    def marshal_to_sibling(tag, attr_dict, index, libvirtxml):
        """
        Convert a sibling tag and attributes to a dict.
        """
        del index
        del libvirtxml
        if tag != 'sibling':
            return None
        return dict(attr_dict)

    @staticmethod
    def marshal_from_cpu(item, index, libvirtxml):
        """
        Convert a dict to cpu tag and attributes.
        """
        del index
        del libvirtxml
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of cpu "
                                         "attributes, not a %s"
                                         % str(item))
        return ('cpu', dict(item))

    @staticmethod
    def marshal_to_cpu(tag, attr_dict, index, libvirtxml):
        """
        Convert a cpu tag and attributes to a dict.
        """
        del index
        del libvirtxml
        if tag != 'cpu':
            return None
        return dict(attr_dict)
