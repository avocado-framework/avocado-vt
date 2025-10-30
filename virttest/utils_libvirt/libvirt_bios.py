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
    current_boot = session.cmd("uname -r").strip()
    kernel_configs = [
        "/boot/config-%s" % current_boot,
        "/usr/lib/modules/%s/config" % current_boot,
    ]
    valid_config = next(
        (c for c in kernel_configs if not session.cmd_status("ls %s" % c)), None
    )
    if not valid_config:
        test.fail("no kernel config found at %s" % kernel_configs)

    if not isinstance(check_list, list):
        check_list = [check_list]
    content = session.cmd("cat %s" % valid_config).strip()
    for item in check_list:
        if item in content:
            test.log.debug("%s content: %s exist", valid_config, item)
        else:
            test.fail("%s content not correct: %s not exist" % (valid_config, item))


def check_uefi_mode(params):
    """
    Deteced if VM is using UEFI/OVMF firmware based on various parameters.

    :param params: Dictionary containing the test parameters
    :return: Boolean, True if UEFI/OVMF mode is detected
    """
    uefi_mode = (
        params.get("firmware", None) == "ovmf"
        or params.get("ovmf_code_filename") is not None
        or params.get("ovmf_vars_filename") is not None
    )

    return uefi_mode
