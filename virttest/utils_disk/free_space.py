"""Guest disk free space utilities."""

import re

from avocado.core import exceptions

from virttest.utils_numeric import normalize_data_size


def get_free_disk(session, mount):
    """Get FreeSpace for given mount point.

    :param session: shell Object.
    :type session: aexpect.ShellSession
    :param mount: mount point(eg. C:, /mnt)
    :type mount: str
    :return: freespace in M-bytes
    :rtype: int
    """
    if re.match(r"[a-zA-Z]:", mount):
        cmd = f"wmic logicaldisk where \"DeviceID='{mount}'\" "
        cmd += "get FreeSpace"
        output = session.cmd_output(cmd)
        digits = re.findall(r"\d+", output)[0]
        free = f"{digits}K"
    else:
        cmd = f"df -h {mount}"
        output = session.cmd_output(cmd)
        free = re.findall(r"\b([\d.]+[BKMGPETZ])\b", output, re.M | re.I)[2]
    free = float(normalize_data_size(free, order_magnitude="M"))
    return int(free)


def check_free_disk(session, mount, required_mb):
    """Check that a guest mount point has enough free space.

    :param session: Guest shell session object.
    :type session: aexpect.ShellSession
    :param mount: Mount point or drive letter (e.g. "/var/tmp", "C:").
    :type mount: str
    :param required_mb: Minimum required free space in MB.
    :type required_mb: int
    :raises exceptions.TestError: When free space is below required_mb.
    """
    free_mb = get_free_disk(session, mount)
    if free_mb < required_mb:
        raise exceptions.TestError(
            f"Not enough space on guest '{mount}': {free_mb}MB free, "
            f"{required_mb}MB required"
        )
