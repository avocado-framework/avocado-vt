"""
A decorator utility functions to apply libvirtd functions.

Copyright: Red Hat Inc. 2020
"""
import logging
import os
import re
from virttest import data_dir

from avocado.utils import process
from avocado.utils import path
from avocado.utils import astring


try:
    path.find_command("libvirtd")
    LIBVIRTD = "libvirtd"
except path.CmdNotFoundError:
    try:
        path.find_command("virtqemud")
        LIBVIRTD = "virtqemud"
    except path.CmdNotFoundError:
        LIBVIRTD = None


def get_libvirtd_split_enable_bit():
    base_cfg_path = os.path.join(data_dir.get_shared_dir(), 'cfg', 'base.cfg')
    if os.path.isfile(base_cfg_path):
        with open(base_cfg_path, 'r') as base_file:
            for line in base_file:
                if 'enable_split_libvirtd_feature' in line and 'yes' in line and '#' not in line:
                    return True
    else:
        logging.info("CAN NOT find base.cfg file")
    return False


def get_libvirt_version_compare(major, minor, update, session=None):
    """
    Determine/use the current libvirt library version on the system
    and compare input major, minor, and update values against it.
    If the running version is greater than or equal to the input
    params version, then return True; otherwise, return False.

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

    if LIBVIRTD is None:
        logging.warn("Can not find command to dertermin libvirt version")
        return False
    libvirt_ver_cmd = "%s -V" % LIBVIRTD
    logging.warn(libvirt_ver_cmd)
    try:
        regex = r'%s\s*.*[Ll]ibvirt.*\s*' % LIBVIRTD
        regex += r'(\d+)\.(\d+)\.(\d+)'
        lines = astring.to_text(func(libvirt_ver_cmd)).splitlines()
        logging.warn("libvirt version value by libvirtd or virtqemud command: %s" % lines)
        for line in lines:
            match = re.search(regex, line.strip())
            if match:
                LIBVIRT_LIB_VERSION = int(match.group(1)) * 1000000 + int(match.group(2)) * 1000 + int(match.group(3))
                break
    except (ValueError, TypeError, AttributeError):
        logging.warn("Error determining libvirt version")
        return False

    compare_version = major * 1000000 + minor * 1000 + update
    if LIBVIRT_LIB_VERSION >= compare_version:
        return True
    return False


LIBVIRTD_SPLIT_ENABLE_BIT = None
IS_LIBVIRTD_SPLIT_VERSION = None


def check_libvirt_version():
    global LIBVIRTD_SPLIT_ENABLE_BIT
    global IS_LIBVIRTD_SPLIT_VERSION
    if LIBVIRTD_SPLIT_ENABLE_BIT is None:
        LIBVIRTD_SPLIT_ENABLE_BIT = get_libvirtd_split_enable_bit()
    if IS_LIBVIRTD_SPLIT_VERSION is None:
        IS_LIBVIRTD_SPLIT_VERSION = get_libvirt_version_compare(5, 6, 0)


def libvirt_version_context_aware_libvirtd_legacy(fn):
    """
    A decorator that must be applied to functions that call if libvirt version <5.6.0.

    :param fn: function name.
    """
    def new_fn(*args, **kwargs):
        """
        Keep previous function as working before if libvirt version< 5.6.0, else do nothing

        :param args: function fixed args.
        :param kwargs: function varied args.
        """
        check_libvirt_version()
        if not IS_LIBVIRTD_SPLIT_VERSION or not LIBVIRTD_SPLIT_ENABLE_BIT:
            logging.warn("legacy start libvirtd daemon NORMALLY with function name: %s" % fn.__name__)
            return fn(*args, **kwargs)
        else:
            logging.warn("legacy start libvirtd daemon IGNORED with function name: %s" % fn.__name__)
            return None
    return new_fn


def libvirt_version_context_aware_libvirtd_split(fn):
    """
    A decorator that must be applied to functions that call if libvirt version >=5.6.0

    :param fn: function name.
    """
    def new_fn(*args, **kwargs):
        """
        Keep previous function as working before if libvirt version>= 5.6.0, else do nothing

        :param args: function fixed args.
        :param kwargs: function varied args.
        """
        check_libvirt_version()
        if IS_LIBVIRTD_SPLIT_VERSION and LIBVIRTD_SPLIT_ENABLE_BIT:
            logging.warn("Split start libvirtd daemon NORMALLY with function name: %s" % fn.__name__)
            return fn(*args, **kwargs)
        else:
            logging.warn("Split start libvirtd daemon IGNORED with function name: %s" % fn.__name__)
            return None
    return new_fn
