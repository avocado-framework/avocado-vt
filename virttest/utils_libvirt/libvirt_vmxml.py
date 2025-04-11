"""
Module simplifying manipulation of the vm attributes described at
http://libvirt.org/formatdomain.html
"""

import logging
import re

from avocado.core import exceptions

from virttest import virsh
from virttest.libvirt_xml import vm_xml
from virttest.libvirt_xml.devices import librarian
from virttest.utils_test import libvirt

LOG = logging.getLogger("avocado." + __name__)


def set_vm_attrs(vmxml, vm_attrs):
    """
    Set element/value pairs in VMXML instance

    :param vmxml: VMXML instance of the domain
    :param vm_attrs: dict of the attribute/value pairs in VMXML
    :return the updated vmxml
    """
    for attr, value in list(vm_attrs.items()):
        LOG.debug("Set %s = %s", attr, value)
        setattr(vmxml, attr, int(value) if value.isdigit() else value)
    vmxml.xmltreefile.write()
    vmxml.sync()
    return vmxml


def check_guest_xml(vm_name, pat_in_dumpxml, option="", status_error=False):
    """
    Check the given pattern in the vm dumpxml

    :param vm_name: vm name
    :param pat_in_dumpxml:  str, the pattern to search in dumpxml
    :param option: str, extra options for dumpxml command
    :param status_error: True if expect not existing, otherwise False
    :raises: TestFail if the result is not expected
    """
    ret_stdout = virsh.dumpxml(vm_name, extra=option).stdout.strip()
    match = re.search(pat_in_dumpxml, ret_stdout)
    found = True if match else False
    prefix_found = "" if found else "not "
    msg = "The pattern '%s' is %sfound in the vm dumpxml" % (
        pat_in_dumpxml,
        prefix_found,
    )
    if found ^ status_error:
        LOG.debug(msg)
    else:
        raise exceptions.TestFail(msg)


def check_guest_machine_type(vmxml, expected_version="9.4.0"):
    """
    Check guest machine type version

    :param vmxml: the guest xml.
    :param expected_version: expected guest machine version, eg
    if <type arch='x86_64' machine='pc-q35-rhel8.2.0'>hvm</type> exists,
    which means expected_version is 8.2.0
    :return: True or False, the flag of checking successfully or not.
    """
    actual_version = re.sub(r"[a-zA-Z]", "", vmxml.os.machine.split("-")[-1])
    LOG.debug("Got guest config machine is rhel{}, ".format(actual_version))

    actual_list = actual_version.split(".")
    expected_list = expected_version.split(".")

    for index in range(len(actual_list)):
        if int(actual_list[index]) > int(expected_list[index]):
            return True
        elif int(actual_list[index]) < int(expected_list[index]):
            return False
    return True


def check_guest_xml_by_xpaths(vmxml, xpaths_text, ignore_status=False):
    """
    Check if the xml has elements/attributes/texts that match all xpaths and texts

    :param xml: Libvirt VMXML instance
    :param xpaths_texts: a structured list containing all elements/attributes
                         xpaths and text to be matched, e.g.:
                        [
                        {'element_attrs': [".//maxMemory[@slots='16']", ".//maxMemory[@unit='KiB']",...,], 'text': '15360000'}
                        {'element_attrs': [".//memory[@unit='KiB']", ..., valuenn], 'text': 'aaa'}
                        {'element_attrs': ["./os/bootmenu[@enable='yes']", ..., valuenn]}
                        ]
    :param ignore_status: boolean, True to not raise an exception when not matched
                                   False to raise an exception when not matched
    :return: boolean, True when matched, False when not matched
    """
    for xpath_text in xpaths_text:
        elem_attrs_list = xpath_text["element_attrs"]
        elem_text = xpath_text.get("text", "")
        for one_elem_attr in elem_attrs_list:
            matches = vmxml.xmltreefile.findall(one_elem_attr)
            if not matches:
                if ignore_status:
                    return False
                else:
                    raise exceptions.TestFail(
                        "XML did not match xpath: %s" % one_elem_attr
                    )
            if elem_text and any([True for x in matches if x.text != elem_text]):
                if ignore_status:
                    return False
                else:
                    raise exceptions.TestFail(
                        "XML did not match text '%s' "
                        "for the xpath '%s'" % (elem_text, one_elem_attr)
                    )
        LOG.debug(
            "Matched the xpaths '%s' with text '%s'" % (elem_attrs_list, elem_text)
        )
    return True


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


def create_vm_device_by_type(dev_type, dev_dict):
    """
    Create device by device type

    :param dev_type: device type
    :param dev_dict: dict for device
    :return: device object
    """
    dev_class = librarian.get(dev_type)
    dev_obj = dev_class()
    dev_obj.setup_attrs(**dev_dict)

    return dev_obj


def modify_vm_device(
    vmxml, dev_type, dev_dict=None, index=0, virsh_instance=virsh, sync_vm=True
):
    """
     Get specified device , update it with given dev_dict if the device exists,
     Create the device if it does not exist

    :param vmxml: domain VMXML instance
    :param dev_type: device type
    :param dev_dict: dict to create device
    :param index: device index
    :param virsh_instance: virsh instance
    :param sync_vm: boolean, True to execute sync, otherwise not
    :return: device object
    """
    dev_obj = None
    try:
        dev_obj, xml_devices = libvirt.get_vm_device(vmxml, dev_type, index=index)
        dev_obj.setup_attrs(**dev_dict)

        vmxml.devices = xml_devices
        vmxml.xmltreefile.write()
        if sync_vm:
            vmxml.sync(virsh_instance=virsh_instance)
    except IndexError:
        dev_obj = create_vm_device_by_type(dev_type, dev_dict)
        libvirt.add_vm_device(
            vmxml, dev_obj, virsh_instance=virsh_instance, sync_vm=sync_vm
        )

    LOG.debug(f"XML of {dev_type} device is:\n{dev_obj}")
    return dev_obj
