"""
Windows virtio-win utilities
"""

import re

from . import drive
from . import system


ARCH_MAP_ISO = {"32-bit": "x86", "64-bit": "amd64"}
ARCH_MAP_VFD = {"32-bit": "i386", "64-bit": "amd64"}


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
