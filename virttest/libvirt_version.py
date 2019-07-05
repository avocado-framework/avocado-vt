"""
Shared code for tests that need to get the libvirt version
"""

import re
import logging

from avocado.utils import process
from virttest.compat_52lts import decode_to_text


def version_compare(major, minor, update, session=None):
    """
    Determine/use the current libvirt library version on the system
    and compare input major, minor, and update values against it.
    If the running version is greater than or equal to the input
    params version, then return True; otherwise, return False

    This is designed to handle upstream version comparisons for
    test adjustments and/or comparisons as a result of upstream
    fixes or changes that could impact test results.

    :param major: Major version to compare against
    :param minor: Minor version to compare against
    :param update: Update value to compare against
    :param session: Shell session on remote host
    :return: True if running version is greater than or
                  equal to the input libvirt version
    """
    LIBVIRT_LIB_VERSION = 0

    func = process.system_output
    if session:
        func = session.cmd_output

    try:
        regex = r'[Uu]sing\s*[Ll]ibrary:\s*[Ll]ibvirt\s*'
        regex += r'(\d+)\.(\d+)\.(\d+)'
        lines = decode_to_text(func("virsh version")).splitlines()
        for line in lines:
            mobj = re.search(regex, line)
            if bool(mobj):
                LIBVIRT_LIB_VERSION = int(mobj.group(1)) * 1000000 + \
                                      int(mobj.group(2)) * 1000 + \
                                      int(mobj.group(3))
                break
    except (ValueError, TypeError, AttributeError):
        logging.warning("Error determining libvirt version")
        return False

    compare_version = major * 1000000 + minor * 1000 + update
    if LIBVIRT_LIB_VERSION >= compare_version:
        return True
    return False
