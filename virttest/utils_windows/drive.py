"""
Windows drive utilities
"""

from . import wmic


def _logical_disks(session, cond=None, props=None):
    cmd = wmic.make_query("LogicalDisk", cond, props,
                          get_swch=wmic.FMT_TYPE_LIST)
    return wmic.parse_list(session.cmd(cmd, timeout=120))


def get_hard_drive_letter(session, label):
    """
    Get hard drive's letter by the given label.

    :param session: Session object.
    :param label: Label pattern string.

    :return: Hard drive's letter if found, otherwise `None`.
    """
    cond = "VolumeName like '%s'" % label
    try:
        return _logical_disks(session, cond=cond, props=["DeviceID"])[0]
    except IndexError:
        return None


def get_floppy_drives_letter(session):
    """
    Get all the floppy drives' letter.

    :param session: Session object.

    :return: Floppy drives' letter.
    """
    cond = "MediaType!=0 AND MediaType!=11 AND MediaType!=12"
    return _logical_disks(session, cond=cond, props=["DeviceID"])
