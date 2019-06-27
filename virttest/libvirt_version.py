"""
Shared code for tests that need to get the libvirt version
"""

import re
import logging

from avocado.utils import process

LIBVIRT_LIB_VERSION = 0


def version_compare(major, minor, update):
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
    :return: True if running version is greater than or
                  equal to the input libvirt version
    """
    global LIBVIRT_LIB_VERSION

    if LIBVIRT_LIB_VERSION == 0:
        try:
            regex = r'[Uu]sing\s*[Ll]ibrary:\s*[Ll]ibvirt\s*'
            regex += r'(\d+)\.(\d+)\.(\d+)'
            lines = process.run("virsh version").stdout_text.splitlines()
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
