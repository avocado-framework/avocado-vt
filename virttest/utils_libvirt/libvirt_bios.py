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
