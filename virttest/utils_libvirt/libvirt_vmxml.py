"""
Module simplifying manipulation of the vm attributes described at
http://libvirt.org/formatdomain.html
"""


import logging
import re

from avocado.core import exceptions

from virttest import virsh
from virttest.libvirt_xml import vm_xml

LOG = logging.getLogger('avocado.' + __name__)


def set_vm_attrs(vmxml, vm_attrs):
    """
    Set element/value pairs in VMXML instance

    :param vmxml: VMXML instance of the domain
    :param vm_attrs: dict of the attribute/value pairs in VMXML
    :return the updated vmxml
    """
    for attr, value in list(vm_attrs.items()):
        LOG.debug('Set %s = %s', attr, value)
        setattr(vmxml, attr, int(value) if value.isdigit() else value)
    vmxml.xmltreefile.write()
    vmxml.sync()
    return vmxml


def check_guest_xml(vm_name, pat_in_dumpxml, option='', status_error=False):
    """
    Check the given pattern in the vm dumpxml

    :param vm_name: vm name
    :param pat_in_dumpxml:  str, the pattern to search in dumpxml
    :param status_error: True if expect not existing, otherwise False
    :raises: TestFail if the result is not expected
    """
    ret_stdout = virsh.dumpxml(vm_name, extra=option).stdout.strip()
    match = re.search(pat_in_dumpxml, ret_stdout)
    found = True if match else False
    prefix_found = '' if found else 'not '
    msg = "The pattern '%s' is %sfound in the vm dumpxml" % (pat_in_dumpxml, prefix_found)
    if found ^ status_error:
        LOG.debug(msg)
    else:
        raise exceptions.TestFail(msg)


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
