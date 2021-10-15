"""
Windows virtio-win utilities
"""

import re
import logging

from . import drive
from . import system
from avocado.core import exceptions


ARCH_MAP_ISO = {"32-bit": "x86", "64-bit": "amd64"}
ARCH_MAP_VFD = {"32-bit": "i386", "64-bit": "amd64"}

LOG = logging.getLogger('avocado.' + __name__)


def arch_dirname_iso(session):
    """
    Get architecture directory's name - iso media version.

    :param session: Session object.

    :return: Directory's name.
    """
    return ARCH_MAP_ISO.get(system.os_arch(session))


def arch_dirname_vfd(session):
    """
    Get architecture directory's name - vfd media version.

    :param session: Session object.

    :return: Directory's name.
    """
    return ARCH_MAP_VFD.get(system.os_arch(session))


def _product_info(session):
    # Some windows system would present 'r' as the registered
    # trademark character at the end of string "Server"
    match = re.search(r"Windows((?: )Serverr?)? (\S+)(?: (R2))?",
                      system.product_name(session), re.I)
    if not match:
        return ("", "", "")
    server, name, suffix = match.groups()
    server = server if server else ""
    suffix = suffix if suffix else ""
    return server, name, suffix


def product_dirname_iso(session):
    """
    Get product directory's name - iso media version.

    :param session: Session object.

    :return: Directory's name.
    """
    server, name, suffix = _product_info(session)
    if not name:
        return None
    if server:
        if len(name) == 4:
            name = re.sub("0+", "k", name)
    else:
        if name[0].isdigit():
            name = "w" + name
    return name + suffix


def product_dirname_vfd(session):
    """
    Get product directory's name - vfd media version.

    :param session: Session object.

    :return: Directory's name.
    """
    server, name, suffix = _product_info(session)
    if not name:
        return None
    return "Win" + name + suffix


def drive_letter_iso(session):
    """
    Get virtio-win drive letter - iso media version.

    :param session: Session object.

    :return: Drive letter.
    """
    return drive.get_hard_drive_letter(session, "virtio-win%")


def drive_letter_vfd(session):
    """
    Get virtio-win drive letter - vfd media version.

    :param session: Session object.

    :return: Drive letter.
    """
    for letter in drive.get_floppy_drives_letter(session):
        # FIXME: addresses the drive accurately
        return letter
    return None


def _get_netkvmco_path(session):
    """
    Get the proper netkvmco.dll path from iso.

    :param session: a session to send cmd
    :return: the proper netkvmco.dll path.
    """

    viowin_ltr = drive_letter_iso(session)
    if not viowin_ltr:
        err = "Could not find virtio-win drive in guest"
        raise exceptions.TestError(err)
    guest_name = product_dirname_iso(session)
    if not guest_name:
        err = "Could not get product dirname of the vm"
        raise exceptions.TestError(err)
    guest_arch = arch_dirname_iso(session)
    if not guest_arch:
        err = "Could not get architecture dirname of the vm"
        raise exceptions.TestError(err)

    middle_path = "%s\\%s" % (guest_name, guest_arch)
    find_cmd = 'dir /b /s %s\\netkvmco.dll | findstr "\\%s\\\\"'
    find_cmd %= (viowin_ltr,  middle_path)
    netkvmco_path = session.cmd(find_cmd).strip()
    LOG.info("Found netkvmco.dll file at %s" % netkvmco_path)
    return netkvmco_path


def prepare_netkvmco(vm):
    """
    Copy the proper netkvmco.dll to driver c:\\, and register it.

    param vm: the target vm
    """
    LOG.info("Prepare the netkvmco.dll")
    session = vm.wait_for_login(timeout=360)
    try:
        netkvmco_path = _get_netkvmco_path(session)
        prepare_netkvmco_cmd = "xcopy %s c:\\ /y && "
        prepare_netkvmco_cmd += "rundll32 netkvmco.dll,"
        prepare_netkvmco_cmd += "RegisterNetKVMNetShHelper"
        session.cmd(prepare_netkvmco_cmd % netkvmco_path, timeout=240)
    finally:
        session.close()
