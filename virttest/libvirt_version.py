"""
Shared code for tests that need to get the libvirt version
"""

import re
import logging

from avocado.core import exceptions
from avocado.utils import path
from avocado.utils import process
from avocado.utils.astring import to_text


LOG = logging.getLogger('avocado.' + __name__)


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
        cmd = "virtqemud"
        if session.cmd_status('which %s' % cmd):
            cmd = "libvirtd"
    else:
        try:
            path.find_command("virtqemud")
            cmd = "virtqemud"
        except path.CmdNotFoundError:
            cmd = "libvirtd"

    try:
        regex = r'\w*d\s*\(libvirt\)\s*'
        regex += r'(\d+)\.(\d+)\.(\d+)'
        lines = to_text(func("%s -V" % cmd)).splitlines()
        for line in lines:
            mobj = re.search(regex, line, re.I)
            if bool(mobj):
                LIBVIRT_LIB_VERSION = int(mobj.group(1)) * 1000000 + \
                                      int(mobj.group(2)) * 1000 + \
                                      int(mobj.group(3))
                break
    except (ValueError, TypeError, AttributeError):
        LOG.warning("Error determining libvirt version")
        return False

    compare_version = major * 1000000 + minor * 1000 + update
    if LIBVIRT_LIB_VERSION == 0:
        LOG.error("Unable to get virtqemud/libvirtd version!")
    elif LIBVIRT_LIB_VERSION >= compare_version:
        return True
    return False


def is_libvirt_feature_supported(params, ignore_error=False):
    """
    Check whether the function is supported in this libvirt version by comparing
    the installed libvirt version

    :param params: Dictionary with the test parameters
    :param ignore_error: Whether to raise an exception
    :raise: When ignore_error is set False, raise TestCancel if the feature is
        not supported
    :return: True if the feature is supported;
        False if the feature is not supported when ignore_error is set to True

    Example:
    ::
    params={'func_supported_since_libvirt_ver':'(6,8,0)'}

    NOTE: The value of 'func_supported_since_libvirt_ver' is a string of
        libvirt's (major, minor, update) version.
    """
    func_supported_since_libvirt_ver = eval(
        params.get("func_supported_since_libvirt_ver", '()'))
    unspported_err_msg = params.get("unspported_err_msg",
                                    "This libvirt version doesn't support "
                                    "this function.")

    if func_supported_since_libvirt_ver:
        if not version_compare(*func_supported_since_libvirt_ver):
            if ignore_error:
                LOG.error(unspported_err_msg)
                return False
            else:
                raise exceptions.TestCancel(unspported_err_msg)
    return True
