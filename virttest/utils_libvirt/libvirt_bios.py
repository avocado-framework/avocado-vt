"""
Libvirt BIOS related utilities.

:copyright: 2022 Red Hat Inc.
"""

import logging

LOG = logging.getLogger("avocado." + __name__)


def remove_bootconfig_items_from_vmos(osxml):
    """
    Remove efi firmware attribute and loader/nvram elements

    :param osxml: VMOSXML object
    :return: VMOSXML, the updated object
    """
    # Remove efi firmware attribute and loader/nvram elements
    # if they exist which may affect newly added same elements
    os_attrs = osxml.fetch_attrs()
    LOG.debug("<os> configuration:%s", os_attrs)
    if os_attrs.get("os_firmware") == "efi":
        osxml.del_os_firmware()
    if os_attrs.get("nvram"):
        osxml.del_nvram()
    if os_attrs.get("loader"):
        osxml.del_loader()
    if os_attrs.get("firmware"):
        osxml.del_firmware()
    return osxml


def check_boot_config(session, test, check_list):
    """
    Check /boot/config-$KVER file.

    :param session: vm session.
    :param test: test object.
    :param check_list: checking list.
    :raises: test.fail if checking fails.
    """
    if not isinstance(check_list, list):
        check_list = [check_list]
    current_boot = session.cmd("uname -r").strip()
    content = session.cmd("cat /boot/config-%s" % current_boot).strip()
    for item in check_list:
        if item in content:
            test.log.debug("/boot/config content: %s exist", item)
        else:
            test.fail("/boot/config content not correct: %s not exist" % item)
