"""
Module simplifying manipulation of XML described at
http://libvirt.org/formatdomain.html
"""

import logging
import platform
import re

from .. import xml_utils
from .. import utils_misc
from ..libvirt_xml import base, accessors, xcepts
from ..libvirt_xml.devices import librarian

LOG = logging.getLogger('avocado.' + __name__)


class VMXMLDevices(list):

    """
    List of device instances from classes handed out by librarian.get()
    """

    @staticmethod
    def __type_check__(other):
        try:
            # Raise error if object isn't dict-like or doesn't have key
            device_tag = other['device_tag']
            # Check that we have support for this type
            librarian.get(device_tag)
        except (AttributeError, TypeError, xcepts.LibvirtXMLError):
            # Required to always raise TypeError for list API in VMXML class
            raise TypeError("Unsupported item type: %s" % str(type(other)))

    def __setitem__(self, key, value):
        self.__type_check__(value)
        super(VMXMLDevices, self).__setitem__(key, value)
        return self

    def append(self, value):
        self.__type_check__(value)
        super(VMXMLDevices, self).append(value)
        return self

    def extend(self, iterable):
        # Make sure __type_check__ happens
        for item in iterable:
            self.append(item)
        return self

    def by_device_tag(self, tag):
        result = VMXMLDevices()
        for device in self:
            if device.device_tag == tag:
                result.append(device)
        return result


class VMXMLBase(base.LibvirtXMLBase):

    """
    Accessor methods for VMXML class properties (items in __slots__)

    Properties:
        hypervisor_type: string, hypervisor type name
            get: return domain's type attribute value
            set: change domain type attribute value
            del: raise excepts.LibvirtXMLError
        vm_name: string, name of the vm
            get: return text value of name tag
            set: set text value of name tag
            del: raise excepts.LibvirtXMLError
        uuid: string, uuid string for vm
            get: return text value of uuid tag
            set: set text value for (new) uuid tag (unvalidated)
            del: remove uuid tag
        title: string, a short description of vm
            get: return text value of title tag
            set: set text value for title tag
            del: remove title tag
        vcpu, memory, max_mem, current_mem, iothreads: integers
            get: returns integer
            set: set integer
            del: removes tag
        dumpcore: string,  control guest OS memory dump
            get: return text value
            set: set 'on' or 'off' for guest OS memory dump
            del: removes tag
        numa_memory: dictionary
            get: return dictionary of numatune/memory attributes
            set: set numatune/memory attributes from dictionary
            del: remove numatune/memory tag
        numa_memnode: list dict of memnode attributes cellid, mode and nodeset
            get: return list of dictionary with numatune/memnode attributes
            set: set multiple numatune/memnode attributes from dictionary list
            del: remove numatune/memnode tag
        on_poweroff: string, action to take when the guest requests a poweroff
            get: returns text value of on_poweroff tag
            set: set test of on_poweroff tag
            del: remove on_poweroff tag
        on_reboot: string, action to take when the guest requests a reboot
            get: returns text value of on_reboot tag
            set: set test of on_reboot tag
            del: remove on_reboot tag
        on_crash: string, action to take when the guest crashes
            get: returns text value of on_crash tag
            set: set test of on_crash tag
            del: remove on_crash tag
        devices: VMXMLDevices (list-like)
            get: returns VMXMLDevices instance for all devices
            set: Define all devices from VMXMLDevices instance
            del: remove all devices
        cputune: VMCPUTuneXML
            get: return VMCPUTuneXML instance for the domain.
            set: Define cputune tag from a VMCPUTuneXML instance.
            del: remove cputune tag
        cpu: VMCPUXML
            get: return VMCPUXML instance for the domain.
            set: Define cpu tag from a VMCPUXML instance.
            del: remove cpu tag
        current_vcpu: string, 'current' attribute of vcpu tag
            get: return a string for 'current' attribute of vcpu
            set: change 'current' attribute of vcpu
            del: remove 'current' attribute of vcpu
        placement: string, 'placement' attribute of vcpu tag
            get: return a string for 'placement' attribute of vcpu
            set: change 'placement' attribute of vcpu
            del: remove 'placement' attribute of vcpu
        cpuset: string, 'cpuset' attribute of vcpu tag
            get: return a string for 'cpuset' attribute of vcpu
            set: change 'cpuset' attribute of vcpu
            del: remove 'cpuset' attribute of vcpu
        vcpus: VMVCPUSXML
            get: return VMVCPUSXML instance for the domain
            set: define vcpus tag from a VMVCPUSXML instance
            del: remove vcpus tag
        emulatorpin: string, cpuset value (see man virsh: cpulist)
            get: return text value of cputune/emulatorpin attributes
            set: set cputune/emulatorpin attributes from string
            del: remove cputune/emulatorpin tag
        features: VMFeaturesXML
            get: return VMFeaturesXML instances for the domain.
            set: define features tag from a VMFeaturesXML instances.
            del: remove features tag
        mem_backing: VMMemBackingXML
            get: return VMMemBackingXML instances for the domain.
            set: define memoryBacking tag from a VMMemBackingXML instances.
            del: remove memoryBacking tag
        max_mem_unit: string, 'unit' attribute of memory
            get: return text value of memory unit attribute
            set: set memory unit attribute
            del: remove memory unit attribute
        current_mem_unit: string, 'unit' attribute of current_memory
            get: return text value of current_memory unit attribute
            set: set current_memory unit attribute
            del: remove current_memory unit attribute
        memory_unit: string, 'unit' attribute of memory
            get: return text value of memory unit attribute
            set: set memory unit attribute
            del: remove memory unit attribute
        memtune: VMMemTuneXML
            get: return VMMemTuneXML instance for the domain.
            set: Define memtune tag from a VMCPUTuneXML instance.
            del: remove memtune tag
    """

    # Additional names of attributes and dictionary-keys instances may contain
    __slots__ = ('hypervisor_type', 'vm_name', 'uuid', 'title', 'vcpu',
                 'max_mem', 'current_mem', 'dumpcore', 'numa_memory',
                 'numa_memnode', 'devices', 'seclabel', 'cputune', 'placement',
                 'cpuset', 'current_vcpu', 'vcpus', 'os', 'cpu', 'pm',
                 'on_poweroff', 'on_reboot', 'on_crash', 'features', 'mb',
                 'max_mem_unit', 'current_mem_unit', 'memtune', 'max_mem_rt',
                 'max_mem_rt_unit', 'max_mem_rt_slots', 'iothreads',
                 'iothreadids', 'memory', 'memory_unit', 'perf', 'keywrap',
                 'sysinfo', 'idmap', 'clock')

    __uncompareable__ = base.LibvirtXMLBase.__uncompareable__

    __schema_name__ = "domain"

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLAttribute(property_name="hypervisor_type",
                               libvirtxml=self,
                               forbidden=None,
                               parent_xpath='/',
                               tag_name='domain',
                               attribute='type')
        accessors.XMLElementText(property_name="vm_name",
                                 libvirtxml=self,
                                 forbidden=None,
                                 parent_xpath='/',
                                 tag_name='name')
        accessors.XMLElementText(property_name="uuid",
                                 libvirtxml=self,
                                 forbidden=None,
                                 parent_xpath='/',
                                 tag_name='uuid')
        accessors.XMLElementText(property_name="title",
                                 libvirtxml=self,
                                 forbidden=None,
                                 parent_xpath='/',
                                 tag_name='title')
        accessors.XMLElementInt(property_name="iothreads",
                                libvirtxml=self,
                                forbidden=None,
                                parent_xpath='/',
                                tag_name='iothreads')
        accessors.XMLElementInt(property_name="vcpu",
                                libvirtxml=self,
                                forbidden=None,
                                parent_xpath='/',
                                tag_name='vcpu')
        accessors.XMLAttribute(property_name="current_vcpu",
                               libvirtxml=self,
                               forbidden=None,
                               parent_xpath='/',
                               tag_name='vcpu',
                               attribute='current')
        accessors.XMLAttribute(property_name="placement",
                               libvirtxml=self,
                               forbidden=None,
                               parent_xpath='/',
                               tag_name='vcpu',
                               attribute='placement')
        accessors.XMLAttribute(property_name="cpuset",
                               libvirtxml=self,
                               forbidden=None,
                               parent_xpath='/',
                               tag_name='vcpu',
                               attribute='cpuset')
        accessors.XMLElementInt(property_name="max_mem",
                                libvirtxml=self,
                                forbidden=None,
                                parent_xpath='/',
                                tag_name='memory')
        accessors.XMLAttribute(property_name="max_mem_unit",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='memory',
                               attribute='unit')
        accessors.XMLAttribute(property_name="dumpcore",
                               libvirtxml=self,
                               forbidden=None,
                               parent_xpath='/',
                               tag_name='memory',
                               attribute='dumpCore')
        accessors.XMLElementInt(property_name="current_mem",
                                libvirtxml=self,
                                forbidden=None,
                                parent_xpath='/',
                                tag_name='currentMemory')
        accessors.XMLAttribute(property_name="current_mem_unit",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='currentMemory',
                               attribute='unit')
        accessors.XMLElementInt(property_name="max_mem_rt",
                                libvirtxml=self,
                                forbidden=None,
                                parent_xpath='/',
                                tag_name='maxMemory')
        accessors.XMLAttribute(property_name="max_mem_rt_slots",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='maxMemory',
                               attribute='slots')
        accessors.XMLAttribute(property_name="max_mem_rt_unit",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='maxMemory',
                               attribute='unit')
        accessors.XMLElementInt(property_name="memory",
                                libvirtxml=self,
                                forbidden=None,
                                parent_xpath='/',
                                tag_name='memory')
        accessors.XMLAttribute(property_name="memory_unit",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='memory',
                               attribute='unit')
        accessors.XMLElementNest(property_name='os',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='os',
                                 subclass=VMOSXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementDict(property_name="numa_memory",
                                 libvirtxml=self,
                                 forbidden=None,
                                 parent_xpath='numatune',
                                 tag_name='memory')
        accessors.XMLElementList(property_name="numa_memnode",
                                 libvirtxml=self,
                                 parent_xpath='numatune',
                                 marshal_from=self.marshal_from_memnode,
                                 marshal_to=self.marshal_to_memnode)
        accessors.XMLElementNest(property_name="perf",
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='perf',
                                 subclass=VMPerfXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest(property_name='cputune',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='cputune',
                                 subclass=VMCPUTuneXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest(property_name='clock',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='clock',
                                 subclass=VMClockXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest(property_name='cpu',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='cpu',
                                 subclass=VMCPUXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest(property_name='vcpus',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='vcpus',
                                 subclass=VMVCPUSXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest(property_name='pm',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='pm',
                                 subclass=VMPMXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementText(property_name="on_poweroff",
                                 libvirtxml=self,
                                 forbidden=None,
                                 parent_xpath='/',
                                 tag_name='on_poweroff')
        accessors.XMLElementText(property_name="on_reboot",
                                 libvirtxml=self,
                                 forbidden=None,
                                 parent_xpath='/',
                                 tag_name='on_reboot')
        accessors.XMLElementText(property_name="on_crash",
                                 libvirtxml=self,
                                 forbidden=None,
                                 parent_xpath='/',
                                 tag_name='on_crash')
        accessors.XMLElementNest(property_name='features',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='features',
                                 subclass=VMFeaturesXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest(property_name='keywrap',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='keywrap',
                                 subclass=VMKeywrapXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest(property_name='mb',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='memoryBacking',
                                 subclass=VMMemBackingXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest(property_name='memtune',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='memtune',
                                 subclass=VMMemTuneXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest(property_name='iothreadids',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='iothreadids',
                                 subclass=VMIothreadidsXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest(property_name='sysinfo',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='sysinfo',
                                 subclass=VMSysinfoXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLElementNest(property_name='idmap',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='idmap',
                                 subclass=VMIDMapXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        super(VMXMLBase, self).__init__(virsh_instance=virsh_instance)

    @staticmethod
    def marshal_from_memnode(item, index, libvirtxml):
        """
        Convert a dict to memnode tag and attributes.
        """
        del index
        del libvirtxml
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of memnode "
                                         "attributes, not a %s"
                                         % str(item))
        return ('memnode', dict(item))

    @staticmethod
    def marshal_to_memnode(tag, attr_dict, index, libvirtxml):
        """
        Convert a memnode tag and attributes to a dict.
        """
        del index
        del libvirtxml
        if tag != 'memnode':
            return None
        return dict(attr_dict)

    def get_devices(self, device_type=None):
        """
        Put all nodes of devices into a VMXMLDevices instance.
        """
        devices = VMXMLDevices()
        all_devices = self.xmltreefile.find('devices')
        if device_type is not None:
            device_nodes = all_devices.findall(device_type)
        else:
            device_nodes = all_devices
        for node in device_nodes:
            device_tag = node.tag
            device_class = librarian.get(device_tag)
            new_one = device_class.new_from_element(node,
                                                    virsh_instance=self.virsh)
            devices.append(new_one)
        return devices

    def set_devices(self, value):
        """
        Define devices based on contents of VMXMLDevices instance
        """
        value_type = type(value)
        if not issubclass(value_type, VMXMLDevices):
            raise xcepts.LibvirtXMLError("Value %s Must be a VMXMLDevices or "
                                         "subclass not a %s"
                                         % (str(value), str(value_type)))
        # Start with clean slate
        exist_dev = self.xmltreefile.find('devices')
        if exist_dev is not None:
            self.del_devices()
        if len(value) > 0:
            devices_element = xml_utils.ElementTree.SubElement(
                self.xmltreefile.getroot(), 'devices')
            for device in value:
                # Separate the element from the tree
                device_element = device.xmltreefile.getroot()
                devices_element.append(device_element)
        self.xmltreefile.write()

    def del_devices(self):
        """
        Remove all devices
        """
        try:
            self.xmltreefile.remove_by_xpath('/devices', remove_all=True)
        except (AttributeError, TypeError):
            pass  # Element already doesn't exist
        self.xmltreefile.write()

    def get_seclabel(self):
        """
        Return seclabel + child attribute dict list or raise LibvirtXML error

        :return: None if no seclabel in xml,
                 list contains dict of seclabel's attributes and children.
        """
        __children_list__ = ['label', 'baselabel', 'imagelabel']

        seclabel_node = self.xmltreefile.findall("seclabel")
        # no seclabel tag found in xml.
        if seclabel_node == []:
            raise xcepts.LibvirtXMLError("Seclabel for this domain does not "
                                         "exist")
        seclabels = []
        for i in range(len(seclabel_node)):
            seclabel = dict(list(seclabel_node[i].items()))
            for child_name in __children_list__:
                child_node = seclabel_node[i].find(child_name)
                if child_node is not None:
                    seclabel[child_name] = child_node.text
            seclabels.append(seclabel)

        return seclabels

    def set_seclabel(self, seclabel_dict_list):
        """
        Set seclabel of vm. Delete all seclabels if seclabel exists, create
        new seclabels use dict values from given seclabel_dict_list in
        xmltreefile.
        """
        __attributs_list__ = ['type', 'model', 'relabel']
        __children_list__ = ['label', 'baselabel', 'imagelabel']

        # check the type of seclabel_dict_list and value.
        if not isinstance(seclabel_dict_list, list):
            raise xcepts.LibvirtXMLError("seclabel_dict_list should be a "
                                         "instance of list, but not a %s.\n"
                                         % type(seclabel_dict_list))
        for seclabel_dict in seclabel_dict_list:
            if not isinstance(seclabel_dict, dict):
                raise xcepts.LibvirtXMLError("value in seclabel_dict_list"
                                             "should be a instance of dict "
                                             "but not a %s.\n"
                                             % type(seclabel_dict))

        seclabel_nodes = self.xmltreefile.findall("seclabel")
        if seclabel_nodes is not None:
            for i in range(len(seclabel_nodes)):
                self.del_seclabel()
        for i in range(len(seclabel_dict_list)):
            seclabel_node = xml_utils.ElementTree.SubElement(
                self.xmltreefile.getroot(),
                "seclabel")

            for key, value in list(seclabel_dict_list[i].items()):
                if key in __children_list__:
                    child_node = seclabel_node.find(key)
                    if child_node is None:
                        child_node = xml_utils.ElementTree.SubElement(
                            seclabel_node,
                            key)
                    child_node.text = value

                elif key in __attributs_list__:
                    seclabel_node.set(key, value)

                else:
                    continue

            self.xmltreefile.write()

    def del_seclabel(self, by_attr=None):
        """
        Remove seclabel tags from a domain. The set of seclabels for removal
        can be restricted by matching attributes in by_attr.
        :param by_attr: List of tuples describing the seclabel to be removed,
        e.g.
        1. [('model', 'selinux'), ('relabel', 'yes')] removes selinux seclabel
         only if relabling is enabled.
        2. [('type', 'dynamic')] removes all seclables that should get unique
         security labels by libvirt.
        3. by_attr=None will remove all seclabel tags.
        """
        tag = "/seclabel"
        try:
            if by_attr:
                for seclabel in self.xmltreefile.findall(tag):
                    if all(attr in seclabel.items() for attr in by_attr):
                        self.xmltreefile.remove(seclabel)
            else:
                self.xmltreefile.remove_by_xpath(tag, remove_all=True)
        except (AttributeError, TypeError):
            pass  # Element already doesn't exist
        self.xmltreefile.write()

    def set_controller(self, controller_list):
        """
        Set controller of vm. Create new controllers use xmltreefile
        from given controller_list.
        """

        # check the type of controller_list and value.
        if not isinstance(controller_list, list):
            raise xcepts.LibvirtXMLError("controller_element_list should be a"
                                         "instance of list, but not a %s.\n"
                                         % type(controller_list))

        devices_element = self.xmltreefile.find("devices")
        for contl in controller_list:
            element = xml_utils.ElementTree.ElementTree(
                file=contl.xml)
            devices_element.append(element.getroot())
        self.xmltreefile.write()

    def del_controller(self, controller_type=None):
        """
        Delete controllers according controller type

        :return: None if deleting all controllers
        """
        # no seclabel tag found in xml.
        del_controllers = self.get_controllers(controller_type=controller_type)
        if del_controllers == []:
            LOG.debug("Controller %s for this domain does not "
                      "exist" % controller_type)

        for controller in del_controllers:
            self.xmltreefile.remove(controller)

    def get_controllers(self, controller_type=None, model=None):
        """
        Get controllers according controller type and/or model type

        :param controller_type: type of controllers need to get
        :param model: model of controllers need to get
        :return: controller list
        """
        all_controllers = self.xmltreefile.findall("devices/controller")
        type_controllers = []
        for controller in all_controllers:
            if ((controller_type is not None and controller.get("type") != controller_type) or
                    (model is not None and model != controller.get("model"))):
                continue
            type_controllers.append(controller)
        return type_controllers


class VMXML(VMXMLBase):

    """
    Higher-level manipulations related to VM's XML or guest/host state
    """

    # Must copy these here or there will be descriptor problems
    __slots__ = []

    def __init__(self, hypervisor_type='kvm', virsh_instance=base.virsh):
        """
        Create new VM XML instance
        """
        super(VMXML, self).__init__(virsh_instance=virsh_instance)
        # Setup some bare-bones XML to build upon
        self.xml = u"<domain type='%s'></domain>" % hypervisor_type

    @staticmethod  # static method (no self) needed b/c calls VMXML.__new__
    def new_from_dumpxml(vm_name, options="", virsh_instance=base.virsh):
        """
        Return new VMXML instance from virsh dumpxml command

        :param vm_name: Name of VM to dumpxml
        :param virsh_instance: virsh module or instance to use
        :return: New initialized VMXML instance
        """
        # TODO: Look up hypervisor_type on incoming XML
        vmxml = VMXML(virsh_instance=virsh_instance)
        result = virsh_instance.dumpxml(vm_name, extra=options)
        vmxml['xml'] = result.stdout_text.strip()
        return vmxml

    @staticmethod
    def new_from_inactive_dumpxml(vm_name, options="", virsh_instance=base.virsh):
        """
        Return new VMXML instance of inactive domain from virsh dumpxml command

        :param vm_name: Name of VM to dumpxml
        :param options: virsh dumpxml command's options
        :param virsh_instance: virsh module or instance to use
        :return: New initialized VMXML instance
        """
        if options.find("--inactive") == -1:
            options += " --inactive"
        return VMXML.new_from_dumpxml(vm_name, options, virsh_instance)

    @staticmethod
    def get_device_class(type_name):
        """
        Return class that handles type_name devices, or raise exception.
        """
        return librarian.get(type_name)

    def undefine(self, options=None, virsh_instance=base.virsh):
        """Undefine this VM with libvirt retaining XML in instance"""
        try:
            nvram = getattr(getattr(self, "os"), "nvram")
        except xcepts.LibvirtXMLNotFoundError:
            nvram = None

        if nvram:
            if options is None:
                options = "--nvram"
            if "--nvram" not in options:
                options += " --nvram"

        return virsh_instance.remove_domain(self.vm_name, options)

    def define(self, virsh_instance=base.virsh):
        """Define VM with virsh from this instance"""
        result = virsh_instance.define(self.xml)
        if result.exit_status:
            LOG.error("Define %s failed.\n"
                      "Detail: %s.", self.vm_name,
                      result.stderr_text)
            return False
        return True

    def sync(self, options=None, virsh_instance=base.virsh):
        """Rebuild VM with the config file."""
        # If target vm no longer exist, this will raise an exception.
        try:
            backup = self.new_from_dumpxml(self.vm_name, virsh_instance=virsh_instance)
        except IOError:
            LOG.debug("Failed to backup %s.", self.vm_name)
            backup = None

        if not self.undefine(options, virsh_instance=virsh_instance):
            raise xcepts.LibvirtXMLError("Failed to undefine %s."
                                         % self.vm_name)
        result_define = virsh_instance.define(self.xml)
        # Vm define failed
        if result_define.exit_status:
            if backup:
                backup.define(virsh_instance=virsh_instance)
            LOG.error("Failed to define %s from xml:\n%s"
                      % (self.vm_name, self.xmltreefile))
            raise xcepts.LibvirtXMLError("Failed to define %s for reason:\n%s"
                                         % (self.vm_name, result_define.stderr_text))

    @staticmethod
    def vm_rename(vm, new_name, uuid=None, virsh_instance=base.virsh):
        """
        Rename a vm from its XML.

        :param vm: VM class type instance
        :param new_name: new name of vm
        :param uuid: new_vm's uuid, if None libvirt will generate.
        :return: a new VM instance or raise LibvirtXMLError
        """
        def _cleanup(details=""):
            backup.define()
            if start_vm:
                vm.start()
            raise xcepts.LibvirtXMLError(details)

        start_vm = False
        if vm.is_alive():
            vm.destroy(gracefully=True)
            start_vm = True
        vmxml = VMXML.new_from_dumpxml(vm.name, virsh_instance=virsh_instance)
        backup = vmxml.copy()

        # Undefine old VM firstly
        if not vmxml.undefine():
            _cleanup(details="Undefine VM %s failed" % vm.name)
        # Alter the XML
        str_old = "domain-" + vm.name
        str_new = "domain-" + new_name
        vmxml.vm_name = new_name
        for channel in vmxml.get_agent_channels():
            for child in channel._children:
                if 'path' in list(child.attrib.keys()):
                    child.attrib['path'] = child.attrib['path'].replace(str_old, str_new)
        if uuid is None:
            # UUID will be regenerated automatically
            del vmxml.uuid
        else:
            vmxml.uuid = uuid
        LOG.debug("Rename %s to %s.", vm.name, new_name)
        if not vmxml.define():
            _cleanup(details="Define VM %s failed" % new_name)
        # Update the name and uuid property for VM object
        vm.name = new_name
        vm.uuid = VMXML.new_from_dumpxml(new_name,
                                         virsh_instance=virsh_instance).uuid
        if uuid is not None and utils_misc.compare_uuid(vm.uuid, uuid) != 0:
            _cleanup(details="UUID %s is not expected %s" % (vm.uuid, uuid))
        if start_vm:
            vm.start()
        return vm

    @staticmethod
    def set_pm_suspend(vm_name, mem="yes", disk="yes", virsh_instance=base.virsh):
        """
        Add/set pm suspend Support

        :params vm_name: Name of defined vm
        :params mem: Enable suspend to memory
        :params disk: Enable suspend to disk
        """
        # Build a instance of class VMPMXML.
        pm = VMPMXML()
        pm.mem_enabled = mem
        pm.disk_enabled = disk
        # Set pm to the new instance.
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        vmxml.pm = pm
        vmxml.sync()

    @staticmethod
    def set_vm_vcpus(vm_name, vcpus, current=None, sockets=None, cores=None,
                     threads=None, add_topology=False, topology_correction=False,
                     update_numa=True, numa_number=None, virsh_instance=base.virsh):
        """
        Convenience method for updating 'vcpu', 'current' and
        'cpu topology' attribute property with of a defined VM

        :param vm_name: Name of defined vm to change vcpu element data
        :param vcpus: New vcpus count, None to delete.
        :param current: New current value, None will not change current value
        :param sockets: number of socket, default None
        :param cores: number of cores, default None
        :param threads: number of threads, default None
        :param add_topology: True to add new topology definition if not present
        :param topology_correction: Correct topology if wrong already
        :param update_numa: Update numa
        :param numa_number: number of numa node
        :parma virsh_instance: virsh instance
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        if vcpus is not None:
            if current is not None:
                try:
                    if(int(current) > vcpus):
                        raise xcepts.LibvirtXMLError("The cpu current value %s "
                                                     "is larger than max "
                                                     "number %s" % (current,
                                                                    vcpus))
                    else:
                        vmxml['current_vcpu'] = current
                except ValueError:
                    raise xcepts.LibvirtXMLError("Invalid 'current' value '%s'"
                                                 % current)
            topology = vmxml.get_cpu_topology()
            if topology:
                if not sockets:
                    sockets = topology['sockets']
                if not cores:
                    cores = topology['cores']
                if not threads:
                    threads = topology['threads']
            if (topology or add_topology) and (sockets or cores or threads):
                # Only operate topology tag, other tags doesn't change
                try:
                    vmcpu_xml = vmxml['cpu']
                except xcepts.LibvirtXMLNotFoundError:
                    LOG.debug("Can not find any cpu tag, now create one.")
                    vmcpu_xml = VMCPUXML()

                if topology_correction and ((int(sockets) * int(cores) * int(threads)) != vcpus):
                    cores = vcpus
                    sockets = 1
                    threads = 1
                vmcpu_xml['topology'] = {'sockets': sockets,
                                         'cores': cores,
                                         'threads': threads}
                vmxml['cpu'] = vmcpu_xml
            try:
                vmcpu_xml = vmxml['cpu']
                if (update_numa and vmxml.cpu.numa_cell):
                    no_numa_cell = len(vmxml.cpu.numa_cell)
                elif numa_number is not None:
                    numa_number = int(numa_number)
                    if 0 < int(numa_number) <= vcpus:
                        no_numa_cell = numa_number
                    else:
                        raise xcepts.LibvirtXMLError("The numa number %d "
                                                     "is larger than vcpus "
                                                     "number %s or not positive" % (numa_number, vcpus))
                if 'no_numa_cell' in locals() and no_numa_cell > 0:
                    if vcpus >= no_numa_cell:
                        vcpus_num = vcpus // no_numa_cell
                        vcpu_rem = vcpus % no_numa_cell
                        index = 0
                        nodexml_list = []
                        for node in range(no_numa_cell):
                            if vmxml.cpu.numa_cell:
                                nodexml = vmcpu_xml.numa_cell[node]
                            else:
                                nodexml = {}
                            if vcpus_num > 1:
                                if (node == no_numa_cell - 1) and vcpu_rem > 0:
                                    nodexml["cpus"] = "%s-%s" % (index, index + vcpus_num + vcpu_rem - 1)
                                else:
                                    nodexml["cpus"] = "%s-%s" % (index, index + vcpus_num - 1)
                            else:
                                if (node == no_numa_cell - 1) and vcpu_rem > 0:
                                    nodexml["cpus"] = str(index + vcpu_rem)
                                else:
                                    nodexml["cpus"] = str(index)
                            if numa_number is not None and numa_number > 0:
                                nodexml['id'] = str(node)
                                cell_mem_size = vmxml.max_mem // numa_number

                                # PPC memory size should align to 256M
                                if 'ppc64le' in platform.machine().lower():
                                    cell_mem_size = (vmxml.max_mem // numa_number // 262144) * 262144
                                nodexml['memory'] = str(cell_mem_size)
                            index = vcpus_num * (node + 1)
                            nodexml_list.append(nodexml)
                        if numa_number is not None and numa_number > 0:
                            vmcpu_xml.xmltreefile.create_by_xpath('/numa')
                            vmcpu_xml.numa_cell = vmcpu_xml.dicts_to_cells(nodexml_list)
                        else:
                            vmcpu_xml.set_numa_cell(vmcpu_xml.dicts_to_cells(nodexml_list))
                    else:
                        LOG.warning("Guest numa could not be updated, expect "
                                    "failures if guest numa is checked")
                vmxml['cpu'] = vmcpu_xml
            except xcepts.LibvirtXMLNotFoundError:
                pass
            vmxml['vcpu'] = vcpus  # call accessor method to change XML
        else:  # value is None
            del vmxml.vcpu
        vmxml.sync()
        # Temporary files for vmxml cleaned up automatically
        # when it goes out of scope here.

    @staticmethod
    def check_cpu_mode(mode):
        """
        Check input cpu mode invalid or not.

        :param mode: the mode of cpu:'host-model'...
        """
        # Possible values for the mode attribute are:
        # "custom", "host-model", "host-passthrough"
        cpu_mode = ["custom", "host-model", "host-passthrough"]
        if mode.strip() not in cpu_mode:
            raise xcepts.LibvirtXMLError(
                "The cpu mode '%s' is invalid!" % mode)

    def get_cpu_topology(self):
        """
        Return cpu topology dict
        """
        topology = {}
        try:
            topology = self.cpu.topology
        except Exception:
            LOG.debug("<cpu>/<topology> xml element not found")
        return topology

    def get_disk_all(self):
        """
        Return VM's disk from XML definition, None if not set

        There is an issue that when the disks have different bus type and same
        target dev value, the previous disk will be overwritten by the last one.
        In order to avoid this problem, you could use get_disk_all_by_expr to
        select all disks by their disk attribute.

        This xml will not return all disks by default parameters:
        <disk type='file' device='disk'>
          <source file='[esx6.7-matrix] xxx/xxx-xxx.vmdk'/>
          <target dev='sda' bus='scsi'/>
          <address type='drive' controller='0' bus='0' target='0' unit='0'/>
        </disk>
        <disk type='file' device='cdrom'>
          <target dev='sda' bus='sata'/>
          <address type='drive' controller='0' bus='0' target='0' unit='0'/>
        </disk>

        """
        disk_nodes = self.xmltreefile.find('devices').findall('disk')
        disks = {}
        for node in disk_nodes:
            dev = node.find('target').get('dev')
            disks[dev] = node
        return disks

    def get_disk_all_by_expr(self, *args):
        """
        Return VM's disk from XML definition by attribute and value
        expression, None if the expression is invalid or no disks are
        found.

        Usage examples:
        1. get_disk_all_by_expr('type==file', 'device!=cdrom')
        2. get_disk_all_by_expr('device==cdrom')

        :param args: attribute and value expression for disks.
                     e.g. device==cdrom, type!=network
        """
        disk_nodes = self.xmltreefile.find('devices').findall('disk')
        disks = {}
        EXPR_PARSER = r'\s*(\w+)\s*(!=|==)\s*(\w+)\s*'
        for node in disk_nodes:
            matched = False
            for expr in args:
                attr_expr = re.search(EXPR_PARSER, expr)
                if not attr_expr:
                    LOG.error("invalid expression: %s", expr)
                    return disks
                attr_name, operator, attr_val = [
                    attr_expr.group(i) for i in range(1, 4)]
                if eval('node.get(attr_name) %s attr_val' % operator):
                    matched = True
                else:
                    matched = False
                    break
            if matched:
                dev = node.find('target').get('dev')
                disks[dev] = node
        return disks

    @staticmethod
    def get_disk_source(vm_name, option="", virsh_instance=base.virsh):
        """
        Get block device  of a defined VM's disks.

        :param vm_name: Name of defined vm.
        :param option: extra option.
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, option,
                                       virsh_instance=virsh_instance)
        disks = vmxml.get_disk_all()
        return list(disks.values())

    @staticmethod
    def get_disk_source_by_expr(vm_name, exprs, option="", virsh_instance=base.virsh):
        """
        Get block device  of a defined VM's disks.

        :param vm_name: Name of defined vm.
        :param option: extra option.
        :param exprs: a string of disk attr and value expressions, multiple expressions are delimited
            by ',', or a list
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, option,
                                       virsh_instance=virsh_instance)
        if isinstance(exprs, str):
            exprs = exprs.split(',')
        if not isinstance(exprs, list):
            raise TypeError('exprs must be a string or a list')
        disks = vmxml.get_disk_all_by_expr(*exprs)
        return list(disks.values())

    @staticmethod
    def get_disk_blk(vm_name, virsh_instance=base.virsh):
        """
        Get block device  of a defined VM's disks.

        :param vm_name: Name of defined vm.
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        disks = vmxml.get_disk_all()
        return list(disks.keys())

    @staticmethod
    def get_disk_count(vm_name, virsh_instance=base.virsh):
        """
        Get count of VM's disks.

        :param vm_name: Name of defined vm.
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        disks = vmxml.get_disk_all()
        if disks is not None:
            return len(disks)
        return 0

    @staticmethod
    def get_disk_count_by_expr(vm_name, exprs, virsh_instance=base.virsh):
        """
        Get count of VM's disks.

        :param vm_name: Name of defined vm.
        :param exprs: A list or string of attribute and value expression for disks.
            if it's a string, the expression must be delimited by ','.
            e.g. device==cdrom, type!=network
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        if isinstance(exprs, str):
            exprs = exprs.split(',')
        if not isinstance(exprs, list):
            raise TypeError('exprs must be a string or a list')
        disks = vmxml.get_disk_all_by_expr(*exprs)
        if disks is not None:
            return len(disks)
        return 0

    @staticmethod
    def get_disk_attr(vm_name, target, tag, attr, virsh_instance=base.virsh):
        """
        Get value of disk tag attribute for a given target dev.
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        attr_value = None
        try:
            disk = vmxml.get_disk_all()[target]
            if tag in ["driver", "boot", "address", "alias", "source"]:
                attr_value = disk.find(tag).get(attr)
        except AttributeError:
            LOG.error("No %s/%s found.", tag, attr)

        return attr_value

    @staticmethod
    def check_disk_exist(vm_name, disk_src, virsh_instance=base.virsh):
        """
        Check if given disk exist in VM.

        :param vm_name: Domain name.
        :param disk_src: Domain disk source path or darget dev.
        :return: True/False
        """
        found = False
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        if not vmxml.get_disk_count(vm_name, virsh_instance=virsh_instance):
            raise xcepts.LibvirtXMLError("No disk in domain %s." % vm_name)
        blk_list = vmxml.get_disk_blk(vm_name, virsh_instance=virsh_instance)
        disk_list = vmxml.get_disk_source(
            vm_name, virsh_instance=virsh_instance)
        try:
            file_list = []
            for disk in disk_list:
                file_list.append(disk.find('source').get('file'))
        except AttributeError:
            LOG.debug("No 'file' type disk.")
        if disk_src in file_list + blk_list:
            found = True
        return found

    @staticmethod
    def check_disk_type(vm_name, disk_src, disk_type, virsh_instance=base.virsh):
        """
        Check if disk type is correct in VM

        :param vm_name: Domain name.
        :param disk_src: Domain disk source path
        :param disk_type: Domain disk type
        :return: True/False
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        if not vmxml.get_disk_count(vm_name, virsh_instance=virsh_instance):
            raise xcepts.LibvirtXMLError("No disk in domain %s." % vm_name)
        disks = vmxml.get_disk_source(vm_name, virsh_instance=virsh_instance)

        found = False
        for disk in disks:
            try:
                disk_dev = ""
                if disk_type == "file":
                    disk_dev = disk.find('source').get('file')
                elif disk_type == "block":
                    disk_dev = disk.find('source').get('dev')
                if disk_src == disk_dev:
                    found = True
            except AttributeError as detail:
                LOG.debug(str(detail))
                continue
        return found

    @staticmethod
    def get_disk_serial(vm_name, disk_target, virsh_instance=base.virsh):
        """
        Get disk serial in VM

        :param vm_name: Domain name.
        :param disk_target: Domain disk target
        :return: disk serial
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        if not vmxml.get_disk_count(vm_name, virsh_instance=virsh_instance):
            raise xcepts.LibvirtXMLError("No disk in domain %s." % vm_name)
        try:
            disk = vmxml.get_disk_all()[disk_target]
        except KeyError:
            raise xcepts.LibvirtXMLError("Wrong disk target:%s." % disk_target)
        serial = ""
        try:
            serial = disk.find("serial").text
        except AttributeError:
            LOG.debug("No serial assigned.")

        return serial

    @staticmethod
    def get_disk_address(vm_name, disk_target, virsh_instance=base.virsh):
        """
        Get disk address in VM

        :param vm_name: Domain name.
        :param disk_target: Domain disk target
        :return: disk address
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        if not vmxml.get_disk_count(vm_name, virsh_instance=virsh_instance):
            raise xcepts.LibvirtXMLError("No disk in domain %s." % vm_name)
        try:
            disk = vmxml.get_disk_all()[disk_target]
        except KeyError:
            raise xcepts.LibvirtXMLError("Wrong disk target:%s." % disk_target)
        address_str = ""
        try:
            disk_bus = disk.find("target").get("bus")
            address = disk.find("address")
            add_type = address.get("type")
            LOG.info("add_type %s", add_type)
            if add_type == "ccw":
                cssid = address.get("cssid")
                ssid = address.get("ssid")
                devno = address.get("devno")
                address_str = "%s:%s.%s.%s" % (add_type, cssid, ssid, devno)
            elif disk_bus == "virtio":
                add_domain = address.get("domain")
                add_bus = address.get("bus")
                add_slot = address.get("slot")
                add_func = address.get("function")
                address_str = ("%s:%s.%s.%s.%s"
                               % (add_type, add_domain, add_bus,
                                  add_slot, add_func))
            elif disk_bus in ["ide", "scsi"]:
                bus = address.get("bus")
                target = address.get("target")
                unit = address.get("unit")
                address_str = "%s:%s.%s.%s" % (disk_bus, bus, target, unit)
        except AttributeError as e:
            raise xcepts.LibvirtXMLError("Get wrong attribute: %s" % str(e))
        return address_str

    @staticmethod
    def get_numa_memory_params(vm_name, virsh_instance=base.virsh):
        """
        Return VM's numa memory setting from XML definition
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        return vmxml.numa_memory

    @staticmethod
    def get_numa_memnode_params(vm_name, virsh_instance=base.virsh):
        """
        Return VM's numa memnode setting from XML definition
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        return vmxml.numa_memnode

    def get_primary_serial(self):
        """
        Get a dict with primary serial features.
        """
        xmltreefile = self.__dict_get__('xml')
        primary_serial = xmltreefile.find('devices').find('serial')
        serial_features = {}
        serial_type = primary_serial.get('type')
        serial_port = primary_serial.find('target').get('port')
        # Support node here for more features
        serial_features['serial'] = primary_serial
        # Necessary features
        serial_features['type'] = serial_type
        serial_features['port'] = serial_port
        return serial_features

    @staticmethod
    def set_primary_serial(vm_name, dev_type, port, path=None,
                           virsh_instance=base.virsh):
        """
        Set primary serial's features of vm_name.

        :param vm_name: Name of defined vm to set primary serial.
        :param dev_type: the type of ``serial:pty,file...``
        :param port: the port of serial
        :param path: the path of serial, it is not necessary for pty
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        xmltreefile = vmxml.__dict_get__('xml')
        try:
            serial = vmxml.get_primary_serial()['serial']
        except AttributeError:
            LOG.debug("Can not find any serial, now create one.")
            # Create serial tree, default is pty
            serial = xml_utils.ElementTree.SubElement(
                xmltreefile.find('devices'),
                'serial', {'type': 'pty'})
            # Create elements of serial target, default port is 0
            xml_utils.ElementTree.SubElement(serial, 'target', {'port': '0'})

        serial.set('type', dev_type)
        serial.find('target').set('port', port)
        # path may not be exist.
        if path is not None:
            serial.find('source').set('path', path)
        else:
            try:
                source = serial.find('source')
                serial.remove(source)
            except AssertionError:
                pass  # Element not found, already removed.
        xmltreefile.write()
        vmxml.set_xml(xmltreefile.name)
        vmxml.undefine()
        vmxml.define()

    def get_agent_channels(self):
        """
        Get all qemu guest agent channels
        """
        ga_channels = []
        try:
            channels = self.xmltreefile.findall("./devices/channel")
            for channel in channels:
                target = channel.find('./target')
                if target is not None:
                    name = target.get('name')
                    if name and name.startswith("org.qemu.guest_agent"):
                        ga_channels.append(channel)
            return ga_channels
        except xcepts.LibvirtXMLError:
            return ga_channels

    def set_agent_channel(self, src_path=None,
                          tgt_name='org.qemu.guest_agent.0',
                          ignore_exist=False):
        """
        Add a channel for guest agent if non exists.

        :param src_path: Source path of the channel
        :param tgt_name: Target name of the channel
        :param ignore_exist: Whether add a channel even if another already exists.
        """
        if not ignore_exist and self.get_agent_channels():
            LOG.debug("Guest agent channel already exists")
            return

        if not src_path:
            src_path = '/var/lib/libvirt/qemu/%s-guest.agent' % self.vm_name
        channel = self.get_device_class('channel')(type_name='unix')
        channel.add_source(mode='bind', path=src_path)
        channel.add_target(type='virtio', name=tgt_name)
        self.devices = self.devices.append(channel)

    def remove_agent_channels(self):
        """
        Delete all channels for guest agent
        """
        for channel in self.get_agent_channels():
            self.xmltreefile.remove(channel)

    def get_iface_all(self):
        """
        Get a dict with interface's mac and node.
        """
        iface_nodes = self.xmltreefile.find('devices').findall('interface')
        interfaces = {}
        for node in iface_nodes:
            mac_addr = node.find('mac').get('address')
            interfaces[mac_addr] = node
        return interfaces

    @staticmethod
    def get_iface_by_mac(vm_name, mac, virsh_instance=base.virsh):
        """
        Get the interface if mac is matched.

        :param vm_name: Name of defined vm.
        :param mac: a mac address.
        :return: return a dict include main interface's features
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        interfaces = vmxml.get_iface_all()
        try:
            interface = interfaces[mac]
        except KeyError:
            interface = None
        if interface is not None:  # matched mac exists.
            features = {}
            iface_type = interface.get('type')
            if iface_type == "direct":
                features['source'] = interface.find('source').attrib
            else:
                features['source'] = interface.find('source').get(iface_type)
            features['type'] = iface_type
            features['mac'] = mac
            if interface.find('target') is not None:
                features['target'] = interface.find('target').attrib
            features['model'] = interface.find('model').get('type')
            if interface.find('bandwidth') is not None:
                if interface.find('bandwidth/outbound') is not None:
                    features['outbound'] = interface.find('bandwidth/outbound').attrib
                if interface.find('bandwidth/inbound') is not None:
                    features['inbound'] = interface.find('bandwidth/inbound').attrib
            if interface.find('backend') is not None:
                features['backend'] = interface.find('backend').attrib
            if interface.find('rom') is not None:
                features['rom'] = interface.find('rom').attrib
            if interface.find('boot') is not None:
                features['boot'] = interface.find('boot').get('order')
            if interface.find('link') is not None:
                features['link'] = interface.find('link').get('state')
            if interface.find('driver') is not None:
                features['driver'] = interface.find('driver').attrib
                if interface.find('driver/host') is not None:
                    features['driver_host'] = interface.find('driver/host').attrib
                if interface.find('driver/guest') is not None:
                    features['driver_guest'] = interface.find('driver/guest').attrib
            if interface.find('alias') is not None:
                features['alias'] = interface.find('alias').attrib
            if interface.find('coalesce') is not None:
                features['coalesce'] = interface.find('coalesce/rx/frames').attrib
            return features
        else:
            return None

    @staticmethod
    def get_iface_dev(vm_name, virsh_instance=base.virsh):
        """
        Return VM's interface device from XML definition, None if not set
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        ifaces = vmxml.get_iface_all()
        if ifaces:
            return list(ifaces.keys())
        return None

    @staticmethod
    def get_first_mac_by_name(vm_name, virsh_instance=base.virsh):
        """
        Convenience method for getting first mac of a defined VM

        :param: vm_name: Name of defined vm to get mac
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        xmltreefile = vmxml.__dict_get__('xml')
        try:
            iface = xmltreefile.find('devices').find('interface')
            return iface.find('mac').get('address')
        except AttributeError:
            return None

    @staticmethod
    def get_iftune_params(vm_name, options="", virsh_instance=base.virsh):
        """
        Return VM's interface tuning setting from XML definition
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, options=options,
                                       virsh_instance=virsh_instance)
        xmltreefile = vmxml.__dict_get__('xml')
        iftune_params = {}
        bandwidth = None
        try:
            bandwidth = xmltreefile.find('devices/interface/bandwidth')
            try:
                iftune_params['inbound'] = bandwidth.find('inbound')
                iftune_params['outbound'] = bandwidth.find('outbound')
            except AttributeError:
                LOG.error("Can't find <inbound> or <outbound> element")
        except AttributeError:
            LOG.error("Can't find <bandwidth> element")

        return iftune_params

    def get_net_all(self):
        """
        Return VM's net from XML definition, None if not set
        """
        xmltreefile = self.__dict_get__('xml')
        net_nodes = xmltreefile.find('devices').findall('interface')
        nets = {}
        for node in net_nodes:
            dev = node.find('target').get('dev')
            nets[dev] = node
        return nets

    @staticmethod
    def set_multiqueues(vm_name, queues, index=0):
        """
        Set multiqueues for interface.

        :param queues: the count of queues for interface
        :param index: the index of interface
        """
        driver_params = {'name': "vhost", 'queues': queues}
        vmxml = VMXML.new_from_dumpxml(vm_name)
        nets = vmxml.__dict_get__('xml').find('devices').findall('interface')
        if index >= len(nets):
            raise xcepts.LibvirtXMLError("Couldn't find %s-th interface for %s"
                                         % (index, vm_name))
        net = nets[index]
        iface = vmxml.get_device_class('interface').new_from_element(net)
        iface.model = "virtio"
        iface.driver = iface.new_driver(driver_attr=driver_params)
        # Update devices: Remove all interfaces and attach new one
        vmxml.__dict_get__('xml').find('devices').remove(net)
        vmxml.devices = vmxml.devices.append(iface)
        vmxml.sync()

    # TODO re-visit this method after the libvirt_xml.devices.interface module
    #     is implemented
    @staticmethod
    def get_net_dev(vm_name):
        """
        Get net device of a defined VM's nets.

        :param vm_name: Name of defined vm.
        """
        vmxml = VMXML.new_from_dumpxml(vm_name)
        nets = vmxml.get_net_all()
        if nets is not None:
            return list(nets.keys())
        return None

    @staticmethod
    def set_cpu_mode(vm_name, mode='host-model', model='',
                     fallback='', match='', check=''):
        """
        Set cpu's mode and respective attributes of VM.

        :param vm_name: Name of defined vm to set cpu mode.
        :param mode: the mode of cpu: host-model, host-passthrough, custom
        :param model: cpu model (power8, core2duo etc)
        :param fallback: forbid, allow*
        :param match: minimum, exact*, strict
        :param check: none, partial, full
        * - default values
        """
        vmxml = VMXML.new_from_dumpxml(vm_name)
        vmxml.check_cpu_mode(mode)
        try:
            cpuxml = vmxml['cpu']
        except xcepts.LibvirtXMLNotFoundError:
            LOG.debug("Can not find any cpu tag, now create one.")
            cpuxml = VMCPUXML()
        cpuxml['mode'] = mode
        if model:
            cpuxml['model'] = model
        if fallback:
            cpuxml['fallback'] = fallback
        if match:
            cpuxml['match'] = match
        if check:
            cpuxml['check'] = check
        vmxml['cpu'] = cpuxml
        vmxml.sync()

    def add_device(self, value, allow_dup=False):
        """
        Add a device into VMXML.

        :param value: instance of device in libvirt_xml/devices/
        :param allow_dup: Boolean value. True for allow to add duplicated devices
        """
        devices = self.get_devices()
        if not allow_dup:
            for device in devices:
                if device == value:
                    LOG.debug("Device %s is already in VM %s.",
                              value, self.vm_name)
                    return
        devices.append(value)
        self.set_devices(devices)

    def del_device(self, value, by_tag=False):
        """
        Remove a device from VMXML

        :param value: instance of device in libvirt_xml/devices/ or device tag
        :param by_tag: Boolean value. True for delete device by tag name
        """
        devices = self.get_devices()
        not_found = True
        for device in devices:
            device_value = device
            if by_tag:
                device_value = device.device_tag
            if device_value == value:
                not_found = False
                devices.remove(device)
                break
        if not_found:
            LOG.debug("Device %s does not exist in VM %s.", value, self.vm_name)
            return
        self.set_devices(devices)

    @staticmethod
    def add_security_info(vmxml, passwd, virsh_instance=base.virsh):
        """
        Add passwd for graphic

        :param vmxml: instance of VMXML
        :param passwd: Password you want to set
        """
        devices = vmxml.devices
        try:
            graphics_index = devices.index(devices.by_device_tag('graphics')[0])
        except IndexError:
            raise xcepts.LibvirtXMLError("No graphics device defined in guest xml")
        graphics = devices[graphics_index]
        graphics.passwd = passwd
        vmxml.devices = devices
        vmxml.define(virsh_instance)

    @staticmethod
    def set_graphics_attr(vm_name, attr, index=0, virsh_instance=base.virsh):
        """
        Set attributes of graphics label of vm xml

        :param vm_name: name of vm
        :param attr: attributes dict to set
        :param index: index of graphics label to set
        :param virsh_instance: virsh instance
        """
        vmxml = VMXML.new_from_inactive_dumpxml(
            vm_name, virsh_instance=virsh_instance)
        graphic = vmxml.xmltreefile.find('devices').findall('graphics')
        for key in attr:
            LOG.debug("Set %s='%s'" % (key, attr[key]))
            graphic[index].set(key, attr[key])
        vmxml.sync(virsh_instance=virsh_instance)

    def get_graphics_devices(self, type_name=""):
        """
        Get all graphics devices or desired type graphics devices

        :param type_name: graphic type, vnc or spice
        """
        devices = self.get_devices()
        graphics_devices = devices.by_device_tag('graphics')
        graphics_list = []
        for graphics_device in graphics_devices:
            graphics_index = devices.index(graphics_device)
            graphics = devices[graphics_index]
            if not type_name:
                graphics_list.append(graphics)
            elif graphics.type_name == type_name:
                graphics_list.append(graphics)
        return graphics_list

    def remove_all_graphics(self):
        """
        Remove all graphics devices.
        """
        self.remove_all_device_by_type('graphics')

    def remove_all_device_by_type(self, device_type):
        """
        Remove all devices of a given type.

        :param type: Type name for devices should be removed.
        """
        try:
            self.xmltreefile.remove_by_xpath(
                '/devices/%s' % device_type,
                remove_all=True)
        except (AttributeError, TypeError):
            pass  # Element already doesn't exist
        self.xmltreefile.write()

    def add_hostdev(self, source_address, mode='subsystem',
                    hostdev_type='pci',
                    managed='yes',
                    boot_order=None):
        """
        Add a hostdev device to guest.

        :param source_address: A dict include slot, function, bus, domain
        """
        dev = self.get_device_class('hostdev')()
        dev.mode = mode
        dev.type = hostdev_type
        dev.managed = managed
        if boot_order:
            dev.boot_order = boot_order
        dev.source = dev.new_source(**source_address)
        self.add_device(dev)

    @staticmethod
    def get_blkio_params(vm_name, options="", virsh_instance=base.virsh):
        """
        Return VM's block I/O setting from XML definition
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, options=options,
                                       virsh_instance=virsh_instance)
        xmltreefile = vmxml.__dict_get__('xml')
        blkio_params = {}
        try:
            blkio = xmltreefile.find('blkiotune')
            try:
                blkio_params['weight'] = blkio.find('weight').text
            except AttributeError:
                LOG.error("Can't find <weight> element")
        except AttributeError:
            LOG.error("Can't find <blkiotune> element")

        if blkio and blkio.find('device'):
            blkio_params['device_weights_path'] = \
                blkio.find('device').find('path').text
            blkio_params['device_weights_weight'] = \
                blkio.find('device').find('weight').text

        return blkio_params

    @staticmethod
    def get_blkdevio_params(vm_name, options="", virsh_instance=base.virsh):
        """
        Return VM's block I/O tuning setting from XML definition
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, options=options,
                                       virsh_instance=virsh_instance)
        xmltreefile = vmxml.__dict_get__('xml')
        blkdevio_params = {}
        iotune = None
        blkdevio_list = ['total_bytes_sec', 'read_bytes_sec',
                         'write_bytes_sec', 'total_iops_sec',
                         'read_iops_sec', 'write_iops_sec']

        # Initialize all of arguments to zero
        for k in blkdevio_list:
            blkdevio_params[k] = 0

        try:
            iotune = xmltreefile.find('/devices/disk/iotune')
            for k in blkdevio_list:
                if iotune.findall(k):
                    blkdevio_params[k] = int(iotune.find(k).text)
        except AttributeError:
            xcepts.LibvirtXMLError("Can't find <iotune> element")

        return blkdevio_params

    @staticmethod
    def set_memoryBacking_tag(vm_name, hpgs=True, nosp=False, locked=False,
                              virsh_instance=base.virsh, access_mode=None,
                              memfd=False):
        """
        let the guest using hugepages.
        """
        # Create a new memoryBacking tag
        mb_xml = VMMemBackingXML()
        mb_xml.nosharepages = nosp
        mb_xml.locked = locked
        if hpgs:
            hpgs = VMHugepagesXML()
            mb_xml.hugepages = hpgs
        if memfd:
            mb_xml.source_type = "memfd"
        if access_mode is not None:
            mb_xml.access_mode = access_mode
        # Set memoryBacking to the new instance.
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        vmxml.mb = mb_xml
        vmxml.sync()

    @staticmethod
    def del_memoryBacking_tag(vm_name, virsh_instance=base.virsh):
        """
        Remove the memoryBacking tag from a domain
        """
        vmxml = VMXML.new_from_dumpxml(vm_name, virsh_instance=virsh_instance)
        try:
            vmxml.xmltreefile.remove_by_xpath(
                "/memoryBacking", remove_all=True)
            vmxml.sync()
        except (AttributeError, TypeError):
            pass  # Element already doesn't exist

    def remove_all_boots(self):
        """
        Remove all OS boots
        """
        try:
            self.xmltreefile.remove_by_xpath('/os/boot', remove_all=True)
        except (AttributeError, TypeError):
            pass  # Element already doesn't exist
        self.xmltreefile.write()

    def set_boot_order_by_target_dev(self, target, order):
        """
        Set boot order by target dev

        :param target: The target dev on host
        :param order: The boot order number
        """
        devices = self.get_devices()
        for device in devices:
            if device.device_tag == "disk":
                if device.target.get("dev") == target:
                    device.boot = order
        self.set_devices(devices)

    def set_boot_attrs_by_target_dev(self, target, **attrs):
        """
        Set boot attributes by target dev

        :param target: The target dev on host
        :param attrs: Dict of boot attributes
        """
        devices = self.get_devices()
        for device in devices:
            if device.device_tag == "disk":
                if device.target.get("dev") == target:
                    for name, value in list(attrs.items()):
                        if name == "order":
                            device.boot = value
                        elif name == "loadparm":
                            device.loadparm = value
        self.set_devices(devices)

    def set_os_attrs(self, **attr_dict):
        """
        Set attributes of VMOSXML

        :param attr_dict: The key words of os attributes
        """
        try:
            os_xml = getattr(self, "os")
            if attr_dict:
                for name, value in list(attr_dict.items()):
                    setattr(os_xml, name, value)
            setattr(self, "os", os_xml)
            self.xmltreefile.write()
        except (AttributeError, TypeError, ValueError) as detail:
            raise xcepts.LibvirtXMLError("Invalid os tag or attribute: %s" % detail)

    def remove_all_disk(self):
        """
        Remove all disk devices.
        """
        self.remove_all_device_by_type('disk')

    @staticmethod
    def set_vm_features(vm_name, **attrs):
        """
        Set attrs of vm features xml

        :param vm_name: The name of vm to be set
        :param attrs: attributes to be set
        """
        vmxml = VMXML.new_from_inactive_dumpxml(vm_name)
        if vmxml.xmltreefile.find('/features'):
            features_xml = vmxml.features
        else:
            features_xml = VMFeaturesXML()
        try:
            for attr_key, value in attrs.items():
                setattr(features_xml, attr_key, value)
            LOG.debug('New features_xml: %s', features_xml)
            vmxml.features = features_xml
            vmxml.sync()
        except (AttributeError, TypeError, ValueError) as detail:
            raise xcepts.LibvirtXMLError(
                "Invalid feature tag or attribute: %s" % detail)


class VMCPUXML(base.LibvirtXMLBase):

    """
    Higher-level manipulations related to VM's XML(CPU)
    """

    # Must copy these here or there will be descriptor problems
    __slots__ = ('model', 'vendor', 'feature_list', 'mode', 'match',
                 'fallback', 'topology', 'numa_cell', 'check',
                 'cache', 'vendor_id', 'interconnects', 'migratable')

    def __init__(self, virsh_instance=base.virsh):
        """
        Create new VMCPU XML instance
        """
        # The set action is for test.
        accessors.XMLAttribute(property_name="mode",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cpu',
                               attribute='mode')
        accessors.XMLAttribute(property_name="match",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cpu',
                               attribute='match')
        accessors.XMLAttribute(property_name="check",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cpu',
                               attribute='check')
        accessors.XMLElementText(property_name="model",
                                 libvirtxml=self,
                                 forbidden=[],
                                 parent_xpath='/',
                                 tag_name='model')
        accessors.XMLElementText(property_name="vendor",
                                 libvirtxml=self,
                                 forbidden=[],
                                 parent_xpath='/',
                                 tag_name='vendor')
        accessors.XMLAttribute(property_name="fallback",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='model',
                               attribute='fallback')
        accessors.XMLAttribute(property_name="vendor_id",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='model',
                               attribute='vendor_id')
        accessors.XMLElementDict(property_name="topology",
                                 libvirtxml=self,
                                 forbidden=[],
                                 parent_xpath='/',
                                 tag_name='topology')
        accessors.XMLElementList(property_name="numa_cell",
                                 libvirtxml=self,
                                 parent_xpath='numa',
                                 marshal_from=self.marshal_from_cells,
                                 marshal_to=self.marshal_to_cells,
                                 has_subclass=True)
        accessors.XMLElementDict(property_name="cache",
                                 libvirtxml=self,
                                 forbidden=[],
                                 parent_xpath='/',
                                 tag_name='cache')
        accessors.XMLElementNest(property_name='interconnects',
                                 libvirtxml=self,
                                 parent_xpath='numa',
                                 tag_name='interconnects',
                                 subclass=VMCPUXML.InterconnectsXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLAttribute(property_name="migratable",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cpu',
                               attribute='migratable')
        # This will skip self.get_feature_list() defined below
        accessors.AllForbidden(property_name="feature_list",
                               libvirtxml=self)
        super(VMCPUXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<cpu/>'

    # Sub-element of cpu
    class InterconnectsXML(base.LibvirtXMLBase):

        """Interconnects element of numa"""

        __slots__ = ('latency', 'bandwidth')

        def __init__(self, virsh_instance=base.virsh):
            """
            Create new Interconnects instance
            """
            accessors.XMLElementList(property_name="latency",
                                     libvirtxml=self,
                                     parent_xpath='/',
                                     marshal_from=self.marshal_from_latency,
                                     marshal_to=self.marshal_to_latency)
            accessors.XMLElementList(property_name="bandwidth",
                                     libvirtxml=self,
                                     parent_xpath='/',
                                     marshal_from=self.marshal_from_bandwidth,
                                     marshal_to=self.marshal_to_bandwidth)
            super(VMCPUXML.InterconnectsXML, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<interconnects/>'

        @staticmethod
        def marshal_from_latency(item, index, libvirtxml):
            """
            Convert a dict to latency tag and attributes.
            """
            del index
            del libvirtxml
            if not isinstance(item, dict):
                raise xcepts.LibvirtXMLError("Expected a dictionary of latency "
                                             "attributes, not a %s"
                                             % str(item))
            return ('latency', dict(item))

        @staticmethod
        def marshal_to_latency(tag, attr_dict, index, libvirtxml):
            """
            Convert a latency tag and attributes to a dict.
            """
            del index
            del libvirtxml
            if tag != 'latency':
                return None
            return dict(attr_dict)

        @staticmethod
        def marshal_from_bandwidth(item, index, libvirtxml):
            """
            Convert a dict to bandwidth tag and attributes.
            """
            del index
            del libvirtxml
            if not isinstance(item, dict):
                raise xcepts.LibvirtXMLError("Expected a dictionary of bandwidth "
                                             "attributes, not a %s"
                                             % str(item))
            return ('bandwidth', dict(item))

        @staticmethod
        def marshal_to_bandwidth(tag, attr_dict, index, libvirtxml):
            """
            Convert a bandwidth tag and attributes to a dict.
            """
            del index
            del libvirtxml
            if tag != 'bandwidth':
                return None
            return dict(attr_dict)

    @staticmethod
    def marshal_from_cells(item, index, libvirtxml):
        """
        Convert an xml object to cache tag and xml element.
        """
        if isinstance(item, NumaCellXML):
            return 'cell', item
        elif isinstance(item, dict):
            cell = NumaCellXML()
            cell.setup_attrs(**item)
            return 'cell', cell
        else:
            raise xcepts.LibvirtXMLError("Expected a list of numa cell "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_cells(tag, new_treefile, index, libvirtxml):
        """
        Convert a cache tag xml element to an object of CellCacheXML.
        """
        if tag != 'cell':
            return None     # Don't convert this item
        newone = NumaCellXML(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone

    def get_feature_list(self):
        """
        Accessor method for feature_list property (in __slots__)
        """
        feature_list = []
        xmltreefile = self.__dict_get__('xml')
        for feature_node in xmltreefile.findall('/feature'):
            feature_list.append(feature_node)
        return feature_list

    def get_feature_index(self, name):
        """
        Get the feature's index in the feature list by given name

        :param name: str, the feature's name
        :return: int, the index of this feature in the feature list
        """
        try:
            return [ftr.get('name') for ftr in self.get_feature_list()].index(name)
        except ValueError as detail:
            raise xcepts.LibvirtXMLError("Invalid feature "
                                         "name '%s':%s " % (name, detail))

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
        Get feature name

        :param num: Number in feature list
        :return: Feature name
        """
        return self.get_feature(num).get('name')

    def get_feature_policy(self, num):
        """
        Get feature policy

        :param num: Number in feature list
        :return: Feature policy
        """
        return self.get_feature(num).get('policy')

    def remove_feature(self, num):
        """
        Remove a feature from xml

        :param num: Number in feature list
        """
        xmltreefile = self.__dict_get__('xml')
        node = xmltreefile.getroot()
        node.remove(self.get_feature(num))

    @staticmethod
    def check_feature_name(value):
        """
        Check feature name valid or not.

        :param value: Feature name
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
        return (value in sys_feature)

    def set_feature(self, num, name='', policy=''):
        """
        Set feature name (and policy) to xml

        :param num: Number in feature list
        :param name: New feature name
        :param policy: New feature policy
        """
        feature_set_node = self.get_feature(num)
        if name:
            feature_set_node.set('name', name)
        if policy:
            feature_set_node.set('policy', policy)

    def add_feature(self, name, policy=''):
        """
        Add a feature element to xml

        :param name: New feature name
        :param policy: New feature policy
        """
        xmltreefile = self.__dict_get__('xml')
        node = xmltreefile.getroot()
        feature_node = {'name': name}
        if policy:
            feature_node.update({'policy': policy})
        xml_utils.ElementTree.SubElement(node, 'feature', feature_node)

    @staticmethod
    def dicts_to_cells(cell_list):
        """
        Convert a list of dict-type numa cell attrs to a list of numa cells
        Only support str of int type of attr value, not support xml sub elements

        :param cell_list: a list of attrs of numa cells
        :return: a list of numa cells
        """
        # Attributes of numa cells should be dict-type.
        if not all([isinstance(attr, dict) for attr in cell_list]):
            raise TypeError('Attributes of numa cells should be dict-type.')

        # Attributes values should be str-type of int-type.
        attr_values = [val for cell_val in cell_list for val in cell_val.values()]
        if not all([isinstance(val, str) or isinstance(val, int) for val in attr_values]):
            raise TypeError('Attributes values should be str-type of int-type.')

        # Convert list of attrs to list of NumaCellXML objects
        cells = [(NumaCellXML(), attrs) for attrs in cell_list]
        [x[0].update(x[1]) for x in cells]
        numa_cells = [x[0] for x in cells]
        return numa_cells

    def remove_numa_cells(self):
        """
        Remove numa cells from xml
        """
        try:
            self.xmltreefile.remove_by_xpath('/numa', remove_all=True)
        except (AttributeError, TypeError):
            pass  # Element already doesn't exist
        self.xmltreefile.write()

    def remove_elem_by_xpath(self, xpath_to_remove, remove_all=True):
        """
        Remove a specified sub element from cpu configuration

        :param xpath_to_remove:  str, like '/model' '/numa'
        :param remove_all: bool, True to remove all findings,
                                 False to remove only one finding
        """
        try:
            self.xmltreefile.remove_by_xpath(xpath_to_remove, remove_all)
        except (AttributeError, TypeError):
            LOG.info("Element '%s' already doesn't exist", xpath_to_remove)
        self.xmltreefile.write()

    @staticmethod
    def from_domcapabilities(domcaps_xml):
        """
        Construct a cpu definition from domcapabilities host-model definition.

        :param domcaps_xml: DomCapabilityXML with host-model definition
        :return: None
        """
        cpu_xml = VMCPUXML()
        cpu_xml['model'] = domcaps_xml.get_hostmodel_name()
        features = domcaps_xml.get_additional_feature_list(
                'host-model', ignore_features=None)
        for feature in features:
            for feature_name, feature_policy in feature.items():
                cpu_xml.add_feature(feature_name, policy=feature_policy)

        return cpu_xml


# Sub-element of cpu/numa
class NumaCellXML(base.LibvirtXMLBase):

    """
    Cell element of numa
    """

    __slots__ = ('id', 'cpus', 'memory', 'unit', 'discard', 'memAccess',
                 'caches', 'distances')

    def __init__(self, virsh_instance=base.virsh):
        """
        Create new Numa_CellXML instance
        """
        accessors.XMLAttribute(property_name="id",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cell',
                               attribute='id')
        accessors.XMLAttribute(property_name="cpus",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cell',
                               attribute='cpus')
        accessors.XMLAttribute(property_name="memory",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cell',
                               attribute='memory')
        accessors.XMLAttribute(property_name="unit",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cell',
                               attribute='unit')
        accessors.XMLAttribute(property_name="discard",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cell',
                               attribute='discard')
        accessors.XMLAttribute(property_name="memAccess",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cell',
                               attribute='memAccess')
        accessors.XMLElementList(property_name="caches",
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 marshal_from=self.marshal_from_caches,
                                 marshal_to=self.marshal_to_caches,
                                 has_subclass=True)
        accessors.XMLElementNest(property_name='distances',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='distances',
                                 subclass=NumaCellXML.CellDistancesXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        super(NumaCellXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<cell/>'

    class CellDistancesXML(base.LibvirtXMLBase):
        """
        Distances of cell
        """

        __slots__ = ('sibling',)

        def __init__(self, virsh_instance=base.virsh):
            """
            Create new CellDistancesXML instance
            """
            accessors.XMLElementList(property_name='sibling',
                                     libvirtxml=self,
                                     parent_xpath='/',
                                     marshal_from=self.marshal_from_sibling,
                                     marshal_to=self.marshal_to_sibling)
            super(NumaCellXML.CellDistancesXML, self).__init__(virsh_instance=virsh_instance)
            self.xml = '<distances/>'

        @staticmethod
        def marshal_from_sibling(item, index, libvirtxml):
            """
            Convert a dict to sibling tag and attributes
            """
            del index
            del libvirtxml
            if not isinstance(item, dict):
                raise xcepts.LibvirtXMLError("Expected a dictionary of sibling "
                                             "attributes, not a %s" % str(item))
            return ('sibling', dict(item))

        @staticmethod
        def marshal_to_sibling(tag, attr_dict, index, libvirtxml):
            """
            Convert a sibling tag and attributes to a dict
            """
            del index
            del libvirtxml
            if tag != 'sibling':
                return None
            return dict(attr_dict)

    @staticmethod
    def marshal_from_caches(item, index, libvirtxml):
        """
        Convert an xml object to cache tag and xml element.
        """
        if isinstance(item, CellCacheXML):
            return 'cache', item
        elif isinstance(item, dict):
            cache = CellCacheXML()
            cache.setup_attrs(**item)
            return 'cache', cache
        else:
            raise xcepts.LibvirtXMLError("Expected a list of cell cache "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_caches(tag, new_treefile, index, libvirtxml):
        """
        Convert a cache tag xml element to an object of CellCacheXML.
        """
        if tag != 'cache':
            return None     # Don't convert this item
        newone = CellCacheXML(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone


class CellCacheXML(base.LibvirtXMLBase):

    """
    Cache of cell
    """

    __slots__ = ('level', 'associativity', 'policy',
                 'size_value', 'size_unit', 'line_value', 'line_unit')

    def __init__(self, virsh_instance=base.virsh):
        """
        Create new CellCacheXML instance
        """
        accessors.XMLAttribute(property_name="level",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cache',
                               attribute='level')
        accessors.XMLAttribute(property_name="associativity",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cache',
                               attribute='associativity')
        accessors.XMLAttribute(property_name="policy",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cache',
                               attribute='policy')
        accessors.XMLAttribute(property_name="size_value",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='size',
                               attribute='value')
        accessors.XMLAttribute(property_name="size_unit",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='size',
                               attribute='unit')
        accessors.XMLAttribute(property_name="line_value",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='line',
                               attribute='value')
        accessors.XMLAttribute(property_name="line_unit",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='line',
                               attribute='unit')
        super(CellCacheXML, self).__init__(
            virsh_instance=virsh_instance)
        self.xml = '<cache/>'


class VMClockXML(base.LibvirtXMLBase):

    """
    Higher-level manipulations related to VM's XML(Clock)
    """

    # Must copy these here or there will be descriptor problems
    __slots__ = ('offset', 'timezone', 'adjustment', 'timers')

    def __init__(self, virsh_instance=base.virsh, offset="utc"):
        """
        Create new VMClock XML instance
        """
        # The set action is for test.
        accessors.XMLAttribute(property_name="offset",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='clock',
                               attribute='offset')
        accessors.XMLAttribute(property_name="timezone",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='clock',
                               attribute='timezone')
        accessors.XMLAttribute(property_name="adjustment",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='clock',
                               attribute='adjustment')
        accessors.XMLElementList(property_name="timers",
                                 libvirtxml=self,
                                 forbidden=[],
                                 parent_xpath="/",
                                 marshal_from=self.marshal_from_timer,
                                 marshal_to=self.marshal_to_timer)
        super(VMClockXML, self).__init__(virsh_instance=virsh_instance)
        # Set default offset for clock
        self.xml = '<clock/>'
        self.offset = offset

    # Sub-element of clock
    class TimerXML(base.LibvirtXMLBase):

        """Timer element of clock"""

        __slots__ = ('name', 'present', 'track', 'tickpolicy', 'frequency',
                     'mode', 'catchup_threshold', 'catchup_slew',
                     'catchup_limit')

        def __init__(self, virsh_instance=base.virsh, timer_name="tsc"):
            """
            Create new TimerXML instance
            """
            # The set action is for test.
            accessors.XMLAttribute(property_name="name",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/clock',
                                   tag_name='timer',
                                   attribute='name')
            accessors.XMLAttribute(property_name="present",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/clock',
                                   tag_name='timer',
                                   attribute='present')
            accessors.XMLAttribute(property_name="track",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/clock',
                                   tag_name='timer',
                                   attribute='track')
            accessors.XMLAttribute(property_name="tickpolicy",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/clock',
                                   tag_name='timer',
                                   attribute='tickpolicy')
            accessors.XMLAttribute(property_name="frequency",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/clock',
                                   tag_name='timer',
                                   attribute='frequency')
            accessors.XMLAttribute(property_name="mode",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/clock',
                                   tag_name='timer',
                                   attribute='mode')
            accessors.XMLAttribute(property_name="catchup_threshold",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/clock/timer',
                                   tag_name='catchup',
                                   attribute='threshold')
            accessors.XMLAttribute(property_name="catchup_slew",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/clock/timer',
                                   tag_name='catchup',
                                   attribute='slew')
            accessors.XMLAttribute(property_name="catchup_limit",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/clock/timer',
                                   tag_name='catchup',
                                   attribute='limit')
            super(VMClockXML.TimerXML, self).__init__(
                virsh_instance=virsh_instance)
            self.xml = '<timer/>'
            # name is mandatory for timer
            self.name = timer_name

        def update(self, attr_dict):
            for attr, value in list(attr_dict.items()):
                setattr(self, attr, value)

    @staticmethod
    def marshal_from_timer(item, index, libvirtxml):
        """Convert a TimerXML instance into tag + attributes"""
        del index
        del libvirtxml
        timer = item.xmltreefile.find("clock/timer")
        try:
            return (timer.tag, dict(list(timer.items())))
        except AttributeError:  # Didn't find timer
            raise xcepts.LibvirtXMLError("Expected a list of timer "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_timer(tag, attr_dict, index, libvirtxml):
        """Convert a tag + attributes to a TimerXML instance"""
        del index
        if tag == 'timer':
            newone = VMClockXML.TimerXML(virsh_instance=libvirtxml.virsh)
            newone.update(attr_dict)
            return newone
        else:
            return None


class CacheTuneXML(base.LibvirtXMLBase):

    """CacheTune XML"""

    __slots__ = ('vcpus', 'caches', 'monitors')

    def __init__(self, virsh_instance=base.virsh):
        """
        Create new CacheTuneXML instance
        """
        accessors.XMLAttribute(property_name="vcpus",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='cachetune',
                               attribute='vcpus')
        accessors.XMLElementList(property_name="caches",
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 marshal_from=self.marshal_from_caches,
                                 marshal_to=self.marshal_to_caches,
                                 has_subclass=True)
        accessors.XMLElementList(property_name="monitors",
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 marshal_from=self.marshal_from_monitors,
                                 marshal_to=self.marshal_to_monitors,
                                 has_subclass=True)

        super(CacheTuneXML, self).__init__(
            virsh_instance=virsh_instance)
        self.xml = '<cachetune/>'

    @staticmethod
    def marshal_from_caches(item, index, libvirtxml):
        """
        Convert an xml object to cache tag and xml element.
        """
        if isinstance(item, CacheTuneXML.CacheXML):
            return 'cache', item
        elif isinstance(item, dict):
            cache = CacheTuneXML.CacheXML()
            cache.setup_attrs(**item)
            return 'cache', cache
        else:
            raise xcepts.LibvirtXMLError("Expected a list of CacheXML "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_caches(tag, new_treefile, index, libvirtxml):
        """
        Convert a cache tag xml element to an object of CacheXML.
        """
        if tag != 'cache':
            return None     # Don't convert this item
        newone = CacheTuneXML.CacheXML(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone

    @staticmethod
    def marshal_from_monitors(item, index, libvirtxml):
        """
        Convert an xml object to monitor tag and xml element.
        """
        if isinstance(item, CacheTuneXML.MonitorXML):
            return 'monitor', item
        elif isinstance(item, dict):
            monitor = CacheTuneXML.MonitorXML()
            monitor.setup_attrs(**item)
            return 'monitor', monitor
        else:
            raise xcepts.LibvirtXMLError("Expected a list of MonitorXML "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_monitors(tag, new_treefile, index, libvirtxml):
        """
        Convert a monitor tag xml element to an object of MonitorXML.
        """
        if tag != 'monitor':
            return None     # Don't convert this item
        newone = CacheTuneXML.MonitorXML(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone

    # Sub-element of CacheTuneXML
    class CacheXML(base.LibvirtXMLBase):

        """Cache element of CacheTuneXML"""

        __slots__ = ('id', 'level', 'type', 'size', 'unit')

        def __init__(self, virsh_instance=base.virsh):
            """
            Create new NodeXML instance
            """
            accessors.XMLAttribute(property_name="id",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/',
                                   tag_name='cache',
                                   attribute='id')
            accessors.XMLAttribute(property_name='level',
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/',
                                   tag_name='cache',
                                   attribute='level')
            accessors.XMLAttribute(property_name="type",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/',
                                   tag_name='cache',
                                   attribute='type')
            accessors.XMLAttribute(property_name='size',
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/',
                                   tag_name='cache',
                                   attribute='size')
            accessors.XMLAttribute(property_name='unit',
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/',
                                   tag_name='cache',
                                   attribute='unit')

            super(CacheTuneXML.CacheXML, self).__init__(
                virsh_instance=virsh_instance)
            self.xml = '<cache/>'

    # Sub-element of CacheTuneXML
    class MonitorXML(base.LibvirtXMLBase):

        """Monitor element of CacheTuneXML"""

        __slots__ = ('level', 'vcpus')

        def __init__(self, virsh_instance=base.virsh):
            """
            Create new MonitorXML instance
            """
            accessors.XMLAttribute(property_name='level',
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/',
                                   tag_name='monitor',
                                   attribute='level')
            accessors.XMLAttribute(property_name="vcpus",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/',
                                   tag_name='monitor',
                                   attribute='vcpus')

            super(CacheTuneXML.MonitorXML, self).__init__(
                virsh_instance=virsh_instance)
            self.xml = '<monitor/>'


class MemoryTuneXML(base.LibvirtXMLBase):

    """Event element of perf"""

    __slots__ = ('vcpus', 'nodes', 'monitors')

    def __init__(self, virsh_instance=base.virsh):
        """
        Create new MemoryTuneXML instance
        """
        accessors.XMLAttribute(property_name="vcpus",
                               libvirtxml=self,
                               forbidden=[],
                               parent_xpath='/',
                               tag_name='memorytune',
                               attribute='vcpus')
        accessors.XMLElementList(property_name="nodes",
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 marshal_from=self.marshal_from_nodes,
                                 marshal_to=self.marshal_to_nodes,
                                 has_subclass=True)
        accessors.XMLElementList(property_name="monitors",
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 marshal_from=self.marshal_from_monitors,
                                 marshal_to=self.marshal_to_monitors,
                                 has_subclass=True)

        super(MemoryTuneXML, self).__init__(
            virsh_instance=virsh_instance)
        self.xml = '<memorytune/>'

    @staticmethod
    def marshal_from_nodes(item, index, libvirtxml):
        """
        Convert an xml object to node tag and xml element.
        """
        if isinstance(item, MemoryTuneXML.NodeXML):
            return 'node', item
        elif isinstance(item, dict):
            node = MemoryTuneXML.NodeXML()
            node.setup_attrs(**item)
            return 'node', node
        else:
            raise xcepts.LibvirtXMLError("Expected a list of NodeXML "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_nodes(tag, new_treefile, index, libvirtxml):
        """
        Convert a node tag xml element to an object of NodeXML.
        """
        if tag != 'node':
            return None     # Don't convert this item
        newone = MemoryTuneXML.NodeXML(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone

    @staticmethod
    def marshal_from_monitors(item, index, libvirtxml):
        """
        Convert an xml object to monitor tag and xml element.
        """
        if isinstance(item, MemoryTuneXML.MonitorXML):
            return 'monitor', item
        elif isinstance(item, dict):
            monitor = MemoryTuneXML.MonitorXML()
            monitor.setup_attrs(**item)
            return 'monitor', monitor
        else:
            raise xcepts.LibvirtXMLError("Expected a list of MonitorXML "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_monitors(tag, new_treefile, index, libvirtxml):
        """
        Convert a monitor tag xml element to an object of MonitorXML.
        """
        if tag != 'monitor':
            return None     # Don't convert this item
        newone = MemoryTuneXML.MonitorXML(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone

    # Sub-element of MemoryTuneXML
    class NodeXML(base.LibvirtXMLBase):

        """Node element of MemoryTuneXML"""

        __slots__ = ('id', 'bandwidth')

        def __init__(self, virsh_instance=base.virsh):
            """
            Create new NodeXML instance
            """
            accessors.XMLAttribute(property_name="id",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/',
                                   tag_name='node',
                                   attribute='id')
            accessors.XMLAttribute(property_name='bandwidth',
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/',
                                   tag_name='node',
                                   attribute='bandwidth')

            super(MemoryTuneXML.NodeXML, self).__init__(
                virsh_instance=virsh_instance)
            self.xml = '<node/>'

    # Sub-element of MemoryTuneXML
    class MonitorXML(base.LibvirtXMLBase):

        """Monitor element of MemoryTuneXML"""

        __slots__ = ('vcpus',)

        def __init__(self, virsh_instance=base.virsh):
            """
            Create new MonitorXML instance
            """
            accessors.XMLAttribute(property_name="vcpus",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/',
                                   tag_name='monitor',
                                   attribute='vcpus')

            super(MemoryTuneXML.MonitorXML, self).__init__(
                virsh_instance=virsh_instance)
            self.xml = '<monitor/>'


class VMCPUTuneXML(base.LibvirtXMLBase):
    """
    CPU tuning tag XML class

    Elements:
        vcpupins:             list of dict - vcpu, cpuset
        iothreadscheds:       list of dict - iothreads, scheduler, priority
        vcpuscheds:           list of dict - vcpus, scheduler
        iothreadpins:         list of dict - iothread, cpuset
        emulatorpin:          attribute    - cpuset
        emulatorsched:        attribute    - scheduler
        shares:               int
        period:               int
        quota:                int
        emulator_period:      int
        emulator_quota:       int
        iothread_period:      int
        iothread_quota:       int
        global_period:        int
        global_quota:         int
    """

    __slots__ = ('vcpupins', 'iothreadscheds', 'vcpuscheds', 'iothreadpins',
                 'emulatorpin', 'emulatorsched', 'shares', 'period', 'quota',
                 'emulator_period', 'emulator_quota',
                 'iothread_period', 'iothread_quota',
                 'global_period', 'global_quota',
                 'cachetunes', 'memorytunes')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementList('vcpupins', self, parent_xpath='/',
                                 marshal_from=self.marshal_from_vcpupins,
                                 marshal_to=self.marshal_to_vcpupins)
        accessors.XMLElementList('vcpuscheds', self, parent_xpath='/',
                                 marshal_from=self.marshal_from_vcpuscheds,
                                 marshal_to=self.marshal_to_vcpuscheds)
        accessors.XMLAttribute('emulatorsched', self, parent_xpath='/',
                               tag_name='emulatorsched', attribute='scheduler')
        accessors.XMLAttribute('emulatorpin', self, parent_xpath='/',
                               tag_name='emulatorpin', attribute='cpuset')
        accessors.XMLElementList('iothreadpins', self, parent_xpath='/',
                                 marshal_from=self.marshal_from_iothreadpins,
                                 marshal_to=self.marshal_to_iothreadpins)
        accessors.XMLElementList('iothreadscheds', self, parent_xpath='/',
                                 marshal_from=self.marshal_from_iothreadscheds,
                                 marshal_to=self.marshal_to_iothreadscheds)
        accessors.XMLElementList('memorytunes', self, parent_xpath='/',
                                 marshal_from=self.marshal_from_memorytunes,
                                 marshal_to=self.marshal_to_memorytunes,
                                 has_subclass=True)
        accessors.XMLElementList('cachetunes', self, parent_xpath='/',
                                 marshal_from=self.marshal_from_cachetunes,
                                 marshal_to=self.marshal_to_cachetunes,
                                 has_subclass=True)
        # pylint: disable=E1133
        for slot in self.__all_slots__:
            if slot in ('shares', 'period', 'quota', 'emulator_period',
                        'emulator_quota', 'iothread_period', 'iothread_quota',
                        'global_period', 'global_quota'):
                accessors.XMLElementInt(slot, self, parent_xpath='/',
                                        tag_name=slot)
        super(VMCPUTuneXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<cputune/>'

    @staticmethod
    def marshal_from_memorytunes(item, index, libvirtxml):
        """
        Convert an xml object to memorytune tag and xml element.
        """
        if isinstance(item, MemoryTuneXML):
            return 'memorytune', item
        elif isinstance(item, dict):
            memorytune = MemoryTuneXML()
            memorytune.setup_attrs(**item)
            return 'memorytune', memorytune
        else:
            raise xcepts.LibvirtXMLError("Expected a list of MemoryTuneXML "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_memorytunes(tag, new_treefile, index, libvirtxml):
        """
        Convert a memorytune tag xml element to an object of MemoryTuneXML.
        """
        if tag != 'memorytune':
            return None     # Don't convert this item
        newone = MemoryTuneXML(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone

    @staticmethod
    def marshal_from_cachetunes(item, index, libvirtxml):
        """
        Convert an xml object to cachetune tag and xml element.
        """
        if isinstance(item, CacheTuneXML):
            return 'cachetune', item
        elif isinstance(item, dict):
            cachetune = CacheTuneXML()
            cachetune.setup_attrs(**item)
            return 'cachetune', cachetune
        else:
            raise xcepts.LibvirtXMLError("Expected a list of cachetune "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_cachetunes(tag, new_treefile, index, libvirtxml):
        """
        Convert a cachetune tag xml element to an object of CacheTuneXML.
        """
        if tag != 'cachetune':
            return None     # Don't convert this item
        newone = CacheTuneXML(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone

    @staticmethod
    def marshal_from_vcpupins(item, index, libvirtxml):
        """
        Convert a dict to vcpupin tag and attributes.
        """
        del index
        del libvirtxml
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of host "
                                         "attributes, not a %s"
                                         % str(item))
        return ('vcpupin', dict(item))

    @staticmethod
    def marshal_to_vcpupins(tag, attr_dict, index, libvirtxml):
        """
        Convert a vcpupin tag and attributes to a dict.
        """
        del index
        del libvirtxml
        if tag != 'vcpupin':
            return None
        return dict(attr_dict)

    @staticmethod
    def marshal_from_vcpuscheds(item, index, libvirtxml):
        """
        Convert a dict to vcpusched tag and attributes.
        """
        del index
        del libvirtxml
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of given "
                                         "attributes, not a %s"
                                         % str(item))
        return ('vcpusched', dict(item))

    @staticmethod
    def marshal_to_vcpuscheds(tag, attr_dict, index, libvirtxml):
        """
        Convert a vcpusched tag and attributes to a dict.
        """
        del index
        del libvirtxml
        if tag != 'vcpusched':
            return None
        return dict(attr_dict)

    @staticmethod
    def marshal_from_iothreadpins(item, index, libvirtxml):
        """
        Convert a dict to iothreadpin tag and attributes.
        """
        del index
        del libvirtxml
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of host "
                                         "attributes, not a %s"
                                         % str(item))
        return ('iothreadpin', dict(item))

    @staticmethod
    def marshal_to_iothreadpins(tag, attr_dict, index, libvirtxml):
        """
        Convert a iothreadpin tag and attributes to a dict.
        """
        del index
        del libvirtxml
        if tag != 'iothreadpin':
            return None
        return dict(attr_dict)

    @staticmethod
    def marshal_from_iothreadscheds(item, index, libvirtxml):
        """
        Convert a dict to iothreadsched tag and attributes.
        """
        del index
        del libvirtxml
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of host "
                                         "attributes, not a %s"
                                         % str(item))
        return ('iothreadsched', dict(item))

    @staticmethod
    def marshal_to_iothreadscheds(tag, attr_dict, index, libvirtxml):
        """
        Convert a iothreadsched tag and attributes to a dict.
        """
        del index
        del libvirtxml
        if tag != 'iothreadsched':
            return None
        return dict(attr_dict)


class VMOSXML(base.LibvirtXMLBase):

    """
    Class to access <os> tag of domain XML.

    Elements:
        os:           list attributes - firmware
        type:         text attributes - arch, machine
        loader:       path
        boots:        list attributes - dev
        bootmenu:          attributes - enable, timeout
        smbios:            attributes - mode
        bios:              attributes - useserial, rebootTimeout
        init:         text
        bootloader:   text
        bootloader_args:   text
        kernel:       text
        initrd:       text
        cmdline:      text
        dtb:          text
        firmware:     list attribute - feature
    TODO:
        initargs:     list
    """

    __slots__ = ('type', 'arch', 'machine', 'loader', 'boots', 'bootmenu_enable',
                 'smbios_mode', 'bios_useserial', 'bios_reboot_timeout', 'init',
                 'bootloader', 'bootloader_args', 'kernel', 'initrd', 'cmdline',
                 'dtb', 'initargs', 'loader_readonly', 'loader_type', 'nvram',
                 'nvram_template', 'secure', 'bootmenu_timeout', 'os_firmware',
                 'firmware')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementText('type', self, parent_xpath='/',
                                 tag_name='type')
        accessors.XMLElementText('loader', self, parent_xpath='/',
                                 tag_name='loader')
        accessors.XMLAttribute('arch', self, parent_xpath='/',
                               tag_name='type', attribute='arch')
        accessors.XMLAttribute('machine', self, parent_xpath='/',
                               tag_name='type', attribute='machine')
        accessors.XMLElementList('boots', self, parent_xpath='/',
                                 marshal_from=self.marshal_from_boots,
                                 marshal_to=self.marshal_to_boots)
        accessors.XMLAttribute('bootmenu_enable', self, parent_xpath='/',
                               tag_name='bootmenu', attribute='enable')
        accessors.XMLAttribute('bootmenu_timeout', self, parent_xpath='/',
                               tag_name='bootmenu', attribute='timeout')
        accessors.XMLAttribute('smbios_mode', self, parent_xpath='/',
                               tag_name='smbios', attribute='mode')
        accessors.XMLAttribute('bios_useserial', self, parent_xpath='/',
                               tag_name='bios', attribute='useserial')
        accessors.XMLAttribute('bios_reboot_timeout', self, parent_xpath='/',
                               tag_name='bios', attribute='rebootTimeout')
        accessors.XMLElementText('bootloader', self, parent_xpath='/',
                                 tag_name='bootloader')
        accessors.XMLElementText('bootloader_args', self, parent_xpath='/',
                                 tag_name='bootloader_args')
        accessors.XMLElementText('kernel', self, parent_xpath='/',
                                 tag_name='kernel')
        accessors.XMLElementText('initrd', self, parent_xpath='/',
                                 tag_name='initrd')
        accessors.XMLElementText('cmdline', self, parent_xpath='/',
                                 tag_name='cmdline')
        accessors.XMLElementText('dtb', self, parent_xpath='/',
                                 tag_name='dtb')
        accessors.XMLElementText('init', self, parent_xpath='/',
                                 tag_name='init')
        accessors.XMLAttribute('loader_readonly', self, parent_xpath='/',
                               tag_name='loader', attribute='readonly')
        accessors.XMLAttribute('loader_type', self, parent_xpath='/',
                               tag_name='loader', attribute='type')
        accessors.XMLAttribute('nvram_template', self, parent_xpath='/',
                               tag_name='nvram', attribute='template')
        accessors.XMLElementText('nvram', self, parent_xpath='/',
                                 tag_name='nvram')
        accessors.XMLAttribute('secure', self, parent_xpath='/',
                               tag_name='loader', attribute='secure')
        accessors.XMLAttribute('os_firmware', self, parent_xpath='/',
                               tag_name='os', attribute='firmware')
        accessors.XMLElementNest('firmware', self, parent_xpath='/',
                                 tag_name='firmware',
                                 subclass=VMOSFWXML,
                                 subclass_dargs={'virsh_instance': virsh_instance})
        super(VMOSXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<os/>'

    @staticmethod
    def marshal_from_boots(item, index, libvirtxml):
        """
        Convert a string to boot tag and attributes.
        """
        del index
        del libvirtxml
        return ('boot', {'dev': item})

    @staticmethod
    def marshal_to_boots(tag, attr_dict, index, libvirtxml):
        """
        Convert a boot tag and attributes to a string.
        """
        del index
        del libvirtxml
        if tag != 'boot':
            return None
        return attr_dict['dev']


class VMPMXML(base.LibvirtXMLBase):

    """
    VM power management tag XML class

    Elements:
        suspend-to-disk:        attribute    - enabled
        suspend-to-mem:         attribute    - enabled
    """

    __slots__ = ('disk_enabled', 'mem_enabled')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLAttribute('disk_enabled', self, parent_xpath='/',
                               tag_name='suspend-to-disk', attribute='enabled')
        accessors.XMLAttribute('mem_enabled', self, parent_xpath='/',
                               tag_name='suspend-to-mem', attribute='enabled')
        super(VMPMXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<pm/>'


class VMFeaturesXML(base.LibvirtXMLBase):

    """
    Class to access <features> tag of domain XML.

    Elements:
        feature_list       list of top level element
        hyperv_relaxed:    attribute - state
        hyperv_vapic:      attribute - state
        hyperv_spinlocks:  attributes - state, retries
        kvm_hidden:        attribute - state
        pvspinlock:        attribute - state
        smm:               attribute - state
    """

    __slots__ = ('feature_list', 'hyperv_relaxed_state', 'hyperv_vapic_state',
                 'hyperv_spinlocks_state', 'hyperv_spinlocks_retries',
                 'hyperv_tlbflush_state', 'hyperv_frequencies_state',
                 'hyperv_reenlightenment_state', 'hyperv_vpindex_state',
                 'kvm_hidden_state', 'pvspinlock_state', 'smm', 'hpt',
                 'htm', 'smm_tseg_unit', 'smm_tseg', 'nested_hv',
                 'pmu', 'kvm_poll_control')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLAttribute(property_name='hyperv_relaxed_state',
                               libvirtxml=self,
                               parent_xpath='/hyperv',
                               tag_name='relaxed',
                               attribute='state')
        accessors.XMLAttribute(property_name='hyperv_vapic_state',
                               libvirtxml=self,
                               parent_xpath='/hyperv',
                               tag_name='vapic',
                               attribute='state')
        accessors.XMLAttribute(property_name='hyperv_spinlocks_state',
                               libvirtxml=self,
                               parent_xpath='/hyperv',
                               tag_name='spinlocks',
                               attribute='state')
        accessors.XMLAttribute(property_name='hyperv_spinlocks_retries',
                               libvirtxml=self,
                               parent_xpath='/hyperv',
                               tag_name='spinlocks',
                               attribute='retries')
        accessors.XMLAttribute(property_name='hyperv_vpindex_state',
                               libvirtxml=self,
                               parent_xpath='/hyperv',
                               tag_name='vpindex',
                               attribute='state')
        accessors.XMLAttribute(property_name='hyperv_tlbflush_state',
                               libvirtxml=self,
                               parent_xpath='/hyperv',
                               tag_name='tlbflush',
                               attribute='state')
        accessors.XMLAttribute(property_name='hyperv_frequencies_state',
                               libvirtxml=self,
                               parent_xpath='/hyperv',
                               tag_name='frequencies',
                               attribute='state')
        accessors.XMLAttribute(property_name='hyperv_reenlightenment_state',
                               libvirtxml=self,
                               parent_xpath='/hyperv',
                               tag_name='reenlightenment',
                               attribute='state')
        accessors.XMLAttribute(property_name='kvm_hidden_state',
                               libvirtxml=self,
                               parent_xpath='/kvm',
                               tag_name='hidden',
                               attribute='state')
        accessors.XMLAttribute(property_name='pvspinlock_state',
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='pvspinlock',
                               attribute='state')
        accessors.XMLAttribute(property_name='smm',
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='smm',
                               attribute='state')
        accessors.XMLAttribute(property_name='smm_tseg_unit',
                               libvirtxml=self,
                               parent_xpath='/smm',
                               tag_name='tseg',
                               attribute='unit')
        accessors.XMLAttribute(property_name='nested_hv',
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='nested-hv',
                               attribute='state')
        accessors.XMLElementText('smm_tseg', self, parent_xpath='/smm',
                                 tag_name='tseg')
        accessors.XMLElementNest(property_name='hpt',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='hpt',
                                 subclass=VMFeaturesHptXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        accessors.XMLAttribute(property_name='htm',
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='htm',
                               attribute='state')
        accessors.XMLAttribute(property_name='pmu',
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='pmu',
                               attribute='state')
        accessors.XMLAttribute(property_name='kvm_poll_control',
                               libvirtxml=self,
                               parent_xpath='/kvm',
                               tag_name='poll-control',
                               attribute='state')
        accessors.AllForbidden(property_name="feature_list",
                               libvirtxml=self)
        super(VMFeaturesXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<features/>'

    def get_feature_list(self):
        """
        Return all features(top level elements) in xml
        """
        feature_list = []
        root = self.__dict_get__('xml').getroot()
        for feature in root:
            feature_list.append(feature.tag)
        return feature_list

    def has_feature(self, name):
        """
        Return true if the given feature exist in xml
        """
        return name in self.get_feature_list()

    def add_feature(self, name, attr_name='', attr_value=''):
        """
        Add a feature element to xml

        :params name: Feature name
        """
        if self.has_feature(name):
            LOG.debug("Feature %s already exist, so remove it", name)
            self.remove_feature(name)
        root = self.__dict_get__('xml').getroot()
        new_attr = {}
        if attr_name:
            new_attr = {attr_name: attr_value}
        xml_utils.ElementTree.SubElement(root, name, new_attr)

    def remove_feature(self, name):
        """
        Remove a feature element from xml

        :params name: Feature name
        """
        root = self.__dict_get__('xml').getroot()
        remove_feature = root.find(name)
        if remove_feature is None:
            LOG.error("Feature %s doesn't exist", name)
        else:
            root.remove(remove_feature)


class VMVCPUSXML(base.LibvirtXMLBase):

    """
    vcpus tag XML class

    Elements:
        vcpu: list of dict - id, enabled, hotpluggable, order
    """

    __slots__ = ('vcpu',)

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementList('vcpu', self, parent_xpath="/",
                                 marshal_from=self.marshal_from_vcpu,
                                 marshal_to=self.marshal_to_vcpu)
        super(VMVCPUSXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<vcpus/>'

    @staticmethod
    def marshal_from_vcpu(item, index, libvirtxml):
        """
        Convert a dict to vcpu tag and attributes
        """
        del index
        del libvirtxml
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError("Expected a dictionary of vcpu "
                                         "attributes, not a %s"
                                         % str(item))
        return ('vcpu', dict(item))

    @staticmethod
    def marshal_to_vcpu(tag, attr_dict, index, libvirtxml):
        """
        Convert a vcpu tag and attributes to a dict
        """
        del index
        del libvirtxml
        if tag != 'vcpu':
            return None
        return dict(attr_dict)


# Sub-element of memoryBacking
class VMHugepagesXML(base.LibvirtXMLBase):

    """hugepages element"""

    __slots__ = ('pages',)

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementList('pages',
                                 libvirtxml=self,
                                 forbidden=[],
                                 parent_xpath="/",
                                 marshal_from=self.marshal_from_page,
                                 marshal_to=self.marshal_to_page)
        super(VMHugepagesXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<hugepages/>'

    # Sub-element of hugepages
    class PageXML(base.LibvirtXMLBase):

        """Page element of hugepages"""

        __slots__ = ('size', 'unit', 'nodeset')

        def __init__(self, virsh_instance=base.virsh):
            """
            Create new PageXML instance
            """
            accessors.XMLAttribute(property_name="size",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/hugepages',
                                   tag_name='page',
                                   attribute='size')
            accessors.XMLAttribute(property_name="unit",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/hugepages',
                                   tag_name='page',
                                   attribute='unit')
            accessors.XMLAttribute(property_name="nodeset",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/hugepages',
                                   tag_name='page',
                                   attribute='nodeset')
            super(VMHugepagesXML.PageXML, self).__init__(
                virsh_instance=virsh_instance)
            self.xml = '<page/>'

        def update(self, attr_dict):
            for attr, value in list(attr_dict.items()):
                setattr(self, attr, value)

    @staticmethod
    def marshal_from_page(item, index, libvirtxml):
        """Convert a PageXML instance into tag + attributes"""
        del index
        del libvirtxml
        page = item.xmltreefile.find("/hugepages/page")
        try:
            return (page.tag, dict(list(page.items())))
        except AttributeError:  # Didn't find page
            raise xcepts.LibvirtXMLError("Expected a list of page "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_page(tag, attr_dict, index, libvirtxml):
        """Convert a tag + attributes to a PageXML instance"""
        del index
        if tag == 'page':
            newone = VMHugepagesXML.PageXML(virsh_instance=libvirtxml.virsh)
            newone.update(attr_dict)
            return newone
        else:
            return None


class VMMemBackingXML(base.LibvirtXMLBase):

    """
    memoryBacking tag XML class

    Elements:
        hugepages
        nosharepages
        locked
        source
        access
        discard
    """

    __slots__ = ('hugepages', 'nosharepages', 'locked', 'source', 'access',
                 'discard', 'source_type', 'access_mode')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementNest(property_name='hugepages',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='hugepages',
                                 subclass=VMHugepagesXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        for slot in ('nosharepages', 'locked', 'discard'):
            accessors.XMLElementBool(slot, self, parent_xpath='/',
                                     tag_name=slot)
        accessors.XMLElementText('source', self, parent_xpath='/',
                                 tag_name='source')
        accessors.XMLAttribute(property_name="source_type",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='source',
                               attribute='type')
        accessors.XMLElementText('access', self, parent_xpath='/',
                                 tag_name='access')
        accessors.XMLAttribute(property_name="access_mode",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='access',
                               attribute='mode')
        super(VMMemBackingXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<memoryBacking/>'


class VMMemTuneXML(base.LibvirtXMLBase):

    """
    Memory Tuning tag XML class

    Element:
        hard_limit:            int
        hard_limit_unit:       attribute
        soft_limit:            int
        soft_limit_unit:       attribute
        swap_hard_limit:       int
        swap_limit_unit:       attribute
        min_guarantee:         int
        min_guarantee_unit:    attribute
    """

    __slots__ = ('hard_limit', 'soft_limit', 'swap_hard_limit', 'min_guarantee',
                 'hard_limit_unit', 'soft_limit_unit', 'swap_limit_unit',
                 'min_guarantee_unit')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementInt(property_name='hard_limit',
                                libvirtxml=self,
                                parent_xpath='/',
                                tag_name='hard_limit')
        accessors.XMLAttribute(property_name="hard_limit_unit",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='hard_limit',
                               attribute='unit')
        accessors.XMLElementInt(property_name='soft_limit',
                                libvirtxml=self,
                                parent_xpath='/',
                                tag_name='soft_limit')
        accessors.XMLAttribute(property_name="soft_limit_unit",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='soft_limit',
                               attribute='unit')
        accessors.XMLElementInt(property_name='swap_hard_limit',
                                libvirtxml=self,
                                parent_xpath='/',
                                tag_name='swap_hard_limit')
        accessors.XMLAttribute(property_name="swap_limit_unit",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='swap_hard_limit',
                               attribute='unit')
        accessors.XMLElementInt(property_name='min_guarantee',
                                libvirtxml=self,
                                parent_xpath='/',
                                tag_name='min_guarantee')
        accessors.XMLAttribute(property_name="min_guarantee_unit",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='min_guarantee',
                               attribute='unit')
        super(VMMemTuneXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<memtune/>'


class VMPerfXML(base.LibvirtXMLBase):

    """
    perf tag XML class

    Properties:
        event :
            dict, keys: name, enabled
    """

    __slots__ = ('events',)

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementList('events', self, forbidden=[],
                                 parent_xpath='/',
                                 marshal_from=self.marshal_from_event,
                                 marshal_to=self.marshal_to_event)

        super(VMPerfXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<perf/>'

    # Sub-element of perf
    class EventXML(base.LibvirtXMLBase):

        """Event element of perf"""

        __slots__ = ('name', 'enabled')

        def __init__(self, virsh_instance=base.virsh):
            """
            Create new EventXML instance
            """
            accessors.XMLAttribute(property_name="name",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/perf',
                                   tag_name='event',
                                   attribute='name')
            accessors.XMLAttribute(property_name="enabled",
                                   libvirtxml=self,
                                   forbidden=[],
                                   parent_xpath='/perf',
                                   tag_name='event',
                                   attribute='enabled')
            super(VMPerfXML.EventXML, self).__init__(
                virsh_instance=virsh_instance)
            self.xml = '<event/>'

        def update(self, attr_dict):
            for attr, value in list(attr_dict.items()):
                setattr(self, attr, value)

    @staticmethod
    def marshal_from_event(item, index, libvirtxml):
        """
        Convert a EventXML instance to tag and attributes
        """
        del index
        del libvirtxml

        event = item.xmltreefile.find("/perf/event")
        try:
            return (event.tag, dict(list(event.items())))
        except AttributeError:  # Didn't find event
            raise xcepts.LibvirtXMLError("Expected a list of event "
                                         "instances, not a %s" % str(item))

    @staticmethod
    def marshal_to_event(tag, attr_dict, index, libvirtxml):
        """
        Convert a tag and attributes to a EventXML instance
        """
        del index
        if tag == 'event':
            newone = VMPerfXML.EventXML(virsh_instance=libvirtxml.virsh)
            newone.update(attr_dict)
            return newone
        else:
            return None


class VMIothreadidsXML(base.LibvirtXMLBase):

    """
    iothreadids tag XML class

    Elements:
        iothread
    """

    __slots__ = ('iothread',)

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementList('iothread', self, parent_xpath='/',
                                 marshal_from=self.marshal_from_iothreads,
                                 marshal_to=self.marshal_to_iothreads)
        super(VMIothreadidsXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<iothreadids/>'

    @staticmethod
    def marshal_from_iothreads(item, index, libvirtxml):
        """
        Convert a string to iothread tag and attributes.
        """
        del index
        del libvirtxml
        return ('iothread', {'id': item})

    @staticmethod
    def marshal_to_iothreads(tag, attr_dict, index, libvirtxml):
        """
        Convert a iothread tag and attributes to a string.
        """
        del index
        del libvirtxml
        if tag != 'iothread':
            return None
        return attr_dict['id']


class VMFeaturesHptXML(base.LibvirtXMLBase):

    """
    Hpt tag XML class of features tag

    Element:
        resizing:               text
        maxpagesize_unit:       attribute
        maxpagesize:            int
    Example:
        <hpt resizing="required">
            <maxpagesize unit="KiB">64</maxpagesize>
        </hpt>
    """

    __slots__ = ('resizing', 'maxpagesize_unit', 'maxpagesize')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLAttribute(property_name="resizing",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='hpt',
                               attribute='resizing')
        accessors.XMLElementInt(property_name='maxpagesize',
                                libvirtxml=self,
                                parent_xpath='/',
                                tag_name='maxpagesize')
        accessors.XMLAttribute(property_name="maxpagesize_unit",
                               libvirtxml=self,
                               parent_xpath='/',
                               tag_name='maxpagesize',
                               attribute='unit')
        super(VMFeaturesHptXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<hpt/>'


class VMKeywrapXML(base.LibvirtXMLBase):
    """
    Keywrap class for s390x ciphers on QEMU
    xpath: /domain/keywrap

    Example:

        vmxml = VMXML.new_from_dumpxml(vm_name)
        kw = VMKeywrapXML()
        kw.set_cipher("aes", "off")
        vmxml.set_keywrap(kw)
    """

    def __init__(self, virsh_instance=base.virsh):
        super(VMKeywrapXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<keywrap/>'

    def get_cipher(self, name):
        """
        Gets cipher 'name' if it exists, else None

        :param name: aes or dea
        :return: cipher element if it exists, else None
        """
        root = self.__dict_get__('xml').getroot()
        for cipher in root.findall('cipher'):
            if cipher.name == name:
                return cipher
        return None

    def set_cipher(self, name, state):
        """
        Sets cipher state for name; adds a new cipher if it doesn't exist yet.

        :param name: aes or dea
        :param state: on or off
        :return: None
        """
        root = self.__dict_get__('xml').getroot()
        cipher = self.get_cipher('name')
        if cipher is not None:
            root.remove(cipher)
        xml_utils.ElementTree.SubElement(root, 'cipher',
                                         {'name': name, 'state': state})


class VMSysinfoXML(base.LibvirtXMLBase):

    """
    Class to access <sysinfo> tag of domain XML

    Elements:
        sysinfo:    list attribute - type
        entry:      text attribute
                    list attributes - entry_name, entry_file
    Example:
        <sysinfo type='fwcfg'>
          <entry name='opt/com.example/name'>example value</entry>
          <entry name='opt/com.example/config' file='/tmp/provision.ign'/>
        </sysinfo>
    """

    __slots__ = ('type', 'entry', 'entry_name', 'entry_file', 'bios')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLAttribute('type', self, parent_xpath='/',
                               tag_name='sysinfo', attribute='type')
        accessors.XMLElementText('entry', self, parent_xpath='/',
                                 tag_name='entry')
        accessors.XMLAttribute('entry_name', self, parent_xpath='/',
                               tag_name='entry', attribute='name')
        accessors.XMLAttribute('entry_file', self, parent_xpath='/',
                               tag_name='entry', attribute='file')
        accessors.XMLElementNest(property_name='bios',
                                 libvirtxml=self,
                                 parent_xpath='/',
                                 tag_name='bios',
                                 subclass=SysinfoBiosXML,
                                 subclass_dargs={
                                     'virsh_instance': virsh_instance})
        super(VMSysinfoXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<sysinfo/>'


class SysinfoBiosXML(base.LibvirtXMLBase):
    """
    bios xml of sysinfo tag

    Example:
        <bios>
          <entry name='vendor'>LENOVO</entry>
        </bios>
    """

    __slots__ = ('entry', 'entry_name')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementText('entry', self, parent_xpath='/',
                                 tag_name='entry')
        accessors.XMLAttribute('entry_name', self, parent_xpath='/',
                               tag_name='entry', attribute='name')
        super(SysinfoBiosXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<bios/>'


class VMIDMapXML(base.LibvirtXMLBase):
    """
    idmap xml class of vmxml

    Example:
      <idmap>
        <uid start='0' target='1000' count='10'/>
        <gid start='0' target='1000' count='10'/>
      </idmap>
    """

    __slots__ = ('uid', 'gid')

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLElementDict(property_name="uid",
                                 libvirtxml=self,
                                 forbidden=None,
                                 parent_xpath='/',
                                 tag_name='uid')
        accessors.XMLElementDict(property_name="gid",
                                 libvirtxml=self,
                                 forbidden=None,
                                 parent_xpath='/',
                                 tag_name='gid')
        super(VMIDMapXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<idmap/>'


# Sub-element of OS XML
class VMOSFWXML(base.LibvirtXMLBase):
    """
    Firmware tag XML class of OS tag
    Elements:
        feature: list of dict - enabled, name
    Example:
        <firmware>
        <feature enabled='yes' name='enrolled-keys'/>
        <feature enabled='yes' name='secure-boot'/>
        </firmware>
    """

    __slots__ = ('feature',)

    def __init__(self, virsh_instance=base.virsh):
        """
        Create new VMOSFWXML instance
        """
        accessors.XMLElementList("feature", self, parent_xpath='/',
                                 marshal_from=self.marshal_from_feature,
                                 marshal_to=self.marshal_to_feature,
                                 has_subclass=True)
        super(VMOSFWXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<firmware/>'

    @staticmethod
    def marshal_from_feature(item, index, libvirtxml):
        """
        Convert a FeatureXML instance into tag and attributes of firmware
        """
        if isinstance(item, FeatureXML):
            return 'feature', item
        elif isinstance(item, dict):
            feature = FeatureXML()
            feature.setup_attrs(**item)
            return 'feature', feature
        else:
            raise xcepts.LibvirtXMLError("Expected a list of feature "
                                         "instance, not a %s" % str(item))

    @staticmethod
    def marshal_to_feature(tag, new_treefile, index, libvirtxml):
        """
        Convert a tag and attributes to a FeatureXML instance
        """
        if tag != 'feature':
            return None
        newone = FeatureXML(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone


# Sub-element of os firmware
class FeatureXML(base.LibvirtXMLBase):
    """Feature element of os firmware"""

    __slots__ = ('enabled', 'name')

    def __init__(self, virsh_instance=base.virsh):
        """
        Create a new FeatureXML instance
        """
        accessors.XMLAttribute("enabled", self, parent_xpath='/',
                               tag_name='feature', attribute='enabled')
        accessors.XMLAttribute("name", self, parent_xpath='/',
                               tag_name='feature', attribute='name')
        super(FeatureXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = '<feature/>'
