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
