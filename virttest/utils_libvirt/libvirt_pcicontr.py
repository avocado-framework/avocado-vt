"""
Accommodate libvirt pci controller utility functions.

:Copyright: 2020 Red Hat Inc.
"""

import logging

from virttest.utils_test import libvirt
from virttest.libvirt_xml import vm_xml

LOG = logging.getLogger('avocado.' + __name__)


def get_max_contr_indexes(vm_xml, cntlr_type, cntlr_model, cntl_num=1):
    """
    Obtain a number of controllers' max indexes in given guest xml

    :param vm_xml: guest xml
    :param cntlr_type: controller type, like pci
    :param cntlr_model: controller model, like pcie-root-port
    :param cntl_num: number of indexes will be returned
    :return: list of max index numbers
    """
    usable_indexes = []
    for elem in vm_xml.devices.by_device_tag('controller'):
        if (cntlr_type == elem.type and cntlr_model == elem.model):
            usable_indexes.append(int(elem.index))
    usable_indexes = sorted(usable_indexes, reverse=True)

    LOG.debug("The indexes returned for controller type '{}' and "
              "controller model '{}' is '{}'".format(cntlr_type,
                                                     cntlr_model,
                                                     usable_indexes[:cntl_num]))
    return usable_indexes[:cntl_num]


def get_free_pci_slot(vm_xml, max_slot=31):
    """
    Get a free slot on pcie-root controller

    :param vm_xml The guest xml
    :param max_slot: the maximum of slot to be selected

    :return: str,the first free slot or None
    """
    used_slot = []
    pci_devices = vm_xml.xmltreefile.find('devices').getchildren()
    for dev in pci_devices:
        address = dev.find('address')
        if (address is not None and address.get('bus') == '0x00'):
            used_slot.append(address.get('slot'))
    LOG.debug("Collect used slot:%s", used_slot)
    for slot_index in range(1, max_slot + 1):
        slot = "%0#4x" % slot_index
        if slot not in used_slot:
            return slot
    return None


def reset_pci_num(vm_name, num=15):
    """
    Reset the number of guest pci, add 15 by default

    :param vm_name: VM name
    :param num: The number of expected pci
    """
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
    # This func only works on aarch64 and x86/q35 machine
    if 'aarch64' in vmxml.os.arch \
            or 'q35' in vmxml.os.machine:
        # Default pcie setting
        pcie_root_port = {'controller_model': 'pcie-root-port', 'controller_type': 'pci'}
        ret_indexes = get_max_contr_indexes(vmxml, 'pci', 'pcie-root-port')
        pcie_to_pci_brg_indexes = get_max_contr_indexes(
            vmxml, 'pci', 'pcie-to-pci-bridge')
        cur_pci_num = ret_indexes[0] if not pcie_to_pci_brg_indexes else \
            max(ret_indexes[0], pcie_to_pci_brg_indexes[0])
        LOG.debug("The current maximum PCI controller index is %d", cur_pci_num)
        if cur_pci_num < num:
            for i in list(range(cur_pci_num + 1, num)):
                pcie_root_port.update({'controller_index': "%d" % i})
                vmxml.add_device(libvirt.create_controller_xml(pcie_root_port))
        else:
            LOG.info("Current pci number is greater than expected")

    # synchronize XML
    vmxml.sync()
