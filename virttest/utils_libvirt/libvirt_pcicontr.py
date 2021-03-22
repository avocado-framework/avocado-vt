"""
Accommodate libvirt pci controller utility functions.

:Copyright: 2020 Red Hat Inc.
"""

import logging


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
            usable_indexes.append(elem.index)
    usable_indexes = sorted(usable_indexes, reverse=True)

    logging.debug("The indexes returned for controller type '{}' and "
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
    logging.debug("Collect used slot:%s", used_slot)
    for slot_index in range(1, max_slot + 1):
        slot = "%0#4x" % slot_index
        if slot not in used_slot:
            return slot
    return None
