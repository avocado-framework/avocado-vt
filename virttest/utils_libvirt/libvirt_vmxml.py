"""
Module simplifying manipulation of the vm attributes described at
http://libvirt.org/formatdomain.html
"""


import logging

from virttest.libvirt_xml import vm_xml


def set_vm_attrs(vmxml, vm_attrs):
    """
    Set element/value pairs in VMXML instance

    :param vmxml: VMXML instance of the domain
    :param vm_attrs: dict of the attribute/value pairs in VMXML
    :return the updated vmxml
    """
    for attr, value in list(vm_attrs.items()):
        logging.debug('Set %s = %s', attr, value)
        setattr(vmxml, attr, int(value) if value.isdigit() else value)
    vmxml.xmltreefile.write()
    vmxml.sync()
    return vmxml


def remove_vm_devices_by_type(vm, device_type):
    """
    Remove devices of a given type.

    :param vm: The vm object.
    :param device_type: Type of devices should be removed.
    """
    vm_was_running = vm.is_alive()
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm.name)
    vmxml.remove_all_device_by_type(device_type)
    vmxml.sync()

    if vm_was_running:
        vm.start()
