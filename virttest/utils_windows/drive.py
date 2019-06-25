"""
Windows drive utilities
"""

from . import wmic
from virttest import utils_misc


def _logical_disks(session, cond=None, props=None):
    cmd = wmic.make_query("LogicalDisk", cond, props,
                          get_swch=wmic.FMT_TYPE_LIST)
    out = utils_misc.wait_for(lambda: wmic.parse_list(session.cmd(cmd,
                              timeout=120)), 240)
    return out if out else []


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


def rescan_disks(session):
    """
    Rescan disks in windows guest.

    :param session: Session object.
    """
    script_path = r"%TEMP%\rescan.dp"
    rescan_cmd = "echo rescan > {0} && diskpart /s {0}"
    session.cmd(rescan_cmd.format(script_path))


def extend_volume(session, vol_id, size=None):
    """
    Extend a volume in windows guest.

    :param session: Session object.
    :param vol_id: Drive letter or Volume number.
    :param size: Default extend the volume to maximum available size,
                 if size is specified, extend the volume to size.
                 The default unit of size is M.
    """
    script_path = r"%TEMP%\extend_{0}.dp".format(vol_id)
    extend_cmd = 'echo select volume %s > {0} && ' % vol_id
    if not size:
        extend_cmd += 'echo extend >> {0} && diskpart /s {0}'
    else:
        extend_cmd += 'echo extend desired=%s >> {0} ' % size
        extend_cmd += '&& diskpart /s {0}'
    session.cmd(extend_cmd.format(script_path))


def shrink_volume(session, vol_id, size):
    """
    Shrink a volume in windows guest.

    :param session: Session object.
    :param vol_id: Drive letter or Volume number.
    :param size: Desired decrease size. The default unit of size is M.
    """
    script_path = r"%TEMP%\shrink_{0}.dp".format(vol_id)
    shrink_cmd = 'echo select volume %s > {0} && ' % vol_id
    shrink_cmd += 'echo shrink desired=%s >> {0} ' % size
    shrink_cmd += '&& diskpart /s {0}'
    session.cmd(shrink_cmd.format(script_path))
