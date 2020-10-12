"""
Module simplifying manipulation of CPU model and topology part described at
http://libvirt.org/formatdomain.html
"""


import logging

from virttest.libvirt_xml import vm_xml
from virttest.utils_libvirt import libvirt_vmxml


def add_cpu_settings(vmxml, params):
    """
    Add cpu element/value pairs to the cpu xml section and keeping the existing
    contents if they are already in the xml. If the numa nodes is added, the
    number of vcpus in nodes should match the number in vcpu element. So, the
    setvm_vcpu pair need to be in params. The same for memory size(max_mem).
    The elements can be updated are list as below:
        setvm_max_mem_rt_slots = "16"
        setvm_max_mem_rt = 8192
        setvm_max_mem_rt_unit = "MiB"
        setvm_max_mem = 1536
        setvm_max_mem_unit = "MiB"
        setvm_current_mem = 1536
        setvm_current_mem_unit = "MiB"
        setvm_vcpu = 4


    :param vmxml: VMXML instance of the domain
    :param params: dict of the cpu related parameter pairs
    :return the updated vmxml
    """
    feature_list = None
    if vmxml.xmltreefile.find('cpu'):
        cpu_xml = vmxml.cpu
        feature_list = cpu_xml.get_feature_list()
    else:
        cpu_xml = vm_xml.VMCPUXML()

    if cpu_xml.xmltreefile.find('mode'):
        cpu_mode = cpu_xml.mode
    else:
        cpu_mode = params.get("cpuxml_cpu_mode", "host-model")

    if cpu_xml.xmltreefile.find("model"):
        cpu_model = cpu_xml.model
    else:
        cpu_model = params.get("cpuxml_model", "")

    if cpu_xml.xmltreefile.find("fallback"):
        cpu_model = cpu_xml.fallback
    else:
        cpu_fallback = params.get("cpuxml_fallback", "forbid")

    cpu_xml_new = vm_xml.VMCPUXML()
    cpu_xml_new.xml = "<cpu><numa/></cpu>"
    cpu_xml_new.mode = cpu_mode
    cpu_xml_new.model = cpu_model
    cpu_xml_new.fallback = cpu_fallback

    feature_name_add = params.get("cpu_feature", None)
    feature_policy_add = params.get("cpu_feature_policy", None)
    if feature_list:
        for i in range(0, len(feature_list)):
            feature_name = cpu_xml.get_feature(i).get('name')
            if feature_name == feature_name_add:
                feature_name_add = ""
            feature_policy = cpu_xml.get_feature(i).get('policy')
            cpu_xml_new.add_feature(feature_name, feature_policy)
    if feature_name_add and feature_policy_add:
        cpu_xml_new.add_feature(feature_name_add, feature_policy_add)

    if cpu_xml.xmltreefile.find('numa'):
        cpu_xml_new.numa_cell = cpu_xml.numa_cell
    else:
        cells = eval(params.get("cpuxml_numa_cell", "[]"))
        cpu_xml_new.numa_cell = vm_xml.VMCPUXML.dicts_to_cells(cells)

        # Update the vcpu and memory values to match the cell config
        # otherwise, the vm may fail to define
        vm_attrs = {k.replace('setvm_', ''): params[k] for k in params
                    if k.startswith('setvm_')}
        logging.debug(vm_attrs)
        libvirt_vmxml.set_vm_attrs(vmxml, vm_attrs)
    vmxml.cpu = cpu_xml_new
    vmxml.xmltreefile.write()
    vmxml.sync()

    return vmxml
