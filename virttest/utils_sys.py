"""
Virtualization test utility functions.

:copyright: 2021 Red Hat Inc.
"""

import logging
import re

from avocado.core import exceptions
from avocado.utils import process

from virttest.utils_misc import cmd_status_output
from virttest.utils_test import libvirt

LOG = logging.getLogger("avocado." + __name__)


# TODO: check function in avocado.utils after the next LTS
def check_dmesg_output(pattern, expect=True, session=None):
    """
    Check whether certain pattern exists in dmesg.

    :param pattern: pattern to search in dmesg
    :param expect: True if expect to exist, False if not
    :param session: session of vm to be checked
    :return: True if result met expectation, False if not met
    """
    dmesg_cmd = "dmesg"
    func_get_dmesg = session.cmd if session else process.run
    dmesg = func_get_dmesg(dmesg_cmd)

    prefix = "" if expect else "Not "
    LOG.info('%sExpecting pattern: "%s".', prefix, pattern)

    # Search for pattern
    found = bool(re.search(pattern, dmesg))
    log_content = ("" if found else "Not") + 'Found "%s"' % pattern
    LOG.debug(log_content)

    if found ^ expect:
        LOG.error("Dmesg output does not meet expectation.")
        return False
    else:
        LOG.info("Dmesg output met expectation")
        return True


def check_audit_log(audit_cmd, match_pattern):
    """
    Check expected match pattern in audit log.

    :param audit_cmd, the executing audit log cmd
    :param match_pattern, the pattern to be checked in audit log.
    """
    ausearch_result = process.run(audit_cmd, shell=True)
    libvirt.check_result(ausearch_result, expected_match=match_pattern)
    LOG.debug("Check audit log %s successfully." % match_pattern)


def get_last_reboot_time(session):
    cmd = "last reboot -F |head -1"

    status, output = cmd_status_output(cmd, shell=True, session=session)
    if status:
        raise exceptions.TestError("Fail to execute the "
                                    "command '%s': error %d: %s" % (cmd,
                                                                    status,
                                                                    output))
    # reboot   system boot  5.14.0-452.el9.a Mon May 27 14:54:05 2024   still running
    match = re.search("\s+(\w+\s+\d+\s+\d+:\d+:\d+\s+\d+)\s", output)
    return match[0].strip() if match else None


def get_host_bridge_id(session=None):
    """
    Get host bridge or root complex on a host

    :param session: vm session object, if none use host pci info
    :return: list of host bridge pci ids
    """
    cmd = "lspci -t"
    hostbridge_regex = r"\[(\d+:\d+)\]"
    status, output = cmd_status_output(cmd, shell=True, session=session)
    if status != 0 or not output:
        return []

    host_bridges = re.findall(hostbridge_regex, output)
    return host_bridges if host_bridges else []
