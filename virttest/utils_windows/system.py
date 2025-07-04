"""
Windows system utilities
"""

import re


def _osinfo(session, props=None):
    cmd = (
        'powershell -command "Get-CimInstance -ClassName Win32_OperatingSystem | Select-Object %s | Format-List *"'
        % (",".join(props))
    )
    out = session.cmd(cmd, timeout=120)
    results = []
    for para in re.split("(?:\r?\n){2,}", out.strip()):
        keys, vals = [], []
        for line in para.splitlines():
            key, val = line.split(":", 1)
            keys.append(key.strip())
            vals.append(val.strip())
        if len(keys) == 1:
            results.append(vals[0])
        else:
            results.append(dict(zip(keys, vals)))
    return results[0] if results else []


def product_name(session):
    """
    Get Windows product name.

    :param session: Session object.

    :return: Windows product name.
    """
    return _osinfo(session, props=["Caption"])


def version(session):
    """
    Get Windows version.

    :param session: Session object.

    :return: Windows version.
    """
    return _osinfo(session, props=["Version"])


def os_arch(session):
    """
    Get Windows OS architecture.

    :param session: Session object.

    :return: Windows OS architecture.
    """
    return _osinfo(session, props=["OSArchitecture"])


def file_exists(session, filename):
    """
    Check if a file exists.

    :param session: Session object.
    :param filename: File name with full path.
    :return: bool value: True if file exists.
    """
    check_cmd = "dir /a /b %s" % filename
    if not session.cmd_status(check_cmd):
        return True
    return False
