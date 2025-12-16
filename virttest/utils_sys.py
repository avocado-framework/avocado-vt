"""
Virtualization test utility functions.

:copyright: 2021 Red Hat Inc.
"""

import logging
import platform
import re

from avocado.utils import process

from virttest.utils_misc import cmd_status_output
from virttest.utils_test import libvirt

LOG = logging.getLogger("avocado." + __name__)

ARCH = platform.machine()


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


def is_image_mode(session=None):
    """
    Check if current OS is in image mode or package mode

    :param session: aexpect session
    :return: boolean, True for image mode, otherwise False
    """
    check_command = "bootc status"
    err_msg = "image:\\s+null"

    def _check_output(status, output):
        LOG.debug("status: %s\noutput:\n%s", status, output)
        if not status:
            result = re.search(err_msg, output) is None
        else:
            result = False
        LOG.debug(
            "Detected %s mode by command '%s'",
            "image" if result else "package",
            check_command,
        )
        return result

    if session:
        status, output = session.cmd_status_output(check_command)
        return _check_output(status, output)
    else:
        ret = process.run(check_command, shell=True, verbose=True, ignore_status=True)
        return _check_output(ret.exit_status, ret.stdout_text)


def get_pids_for(process_names, sort_pids=True, session=None):
    """
    Given a list of names, retrieve the PIDs for
    matching processes. Sort of equivalent
    to: 'ps aux | grep name'

    :param process_names: List of process names to look for
    """

    status, ps_cmd = cmd_status_output("ps aux", shell=True, session=session)
    if status != 0 or not ps_cmd:
        return []

    ps_output = ps_cmd.split("\n")
    relevant_procs = [
        proc
        for proc in ps_output
        for wanted_name in process_names
        if wanted_name in proc
    ]

    relevant_procs = [line.split() for line in relevant_procs]
    relevant_pids = [int(proc[1]) for proc in relevant_procs]

    if sort_pids:
        relevant_pids.sort()

    return relevant_pids


def get_location_code(pci_id):
    """
    Retrieves the location code for a PCI device using the `cat` command.

    :param pci_id : The PCI device address in the format 'xxxx:xx:xx.x'.
    :return: location code if available, or an error message.
             Example location code = 'U898B.NT0.WDS0DT1-P0-C4-T0'
    """
    try:
        if ARCH == "ppc64le":
            loc_code_path = "/sys/bus/pci/devices/%s/of_node/ibm,loc-code" % pci_id
        else:
            raise FileNotFoundError(
                "Valid location code path is not defined for architecture: %s" % ARCH
            )
        with open(loc_code_path, "r") as f:
            loc_code = f.read().strip()
        loc_code = "".join(c for c in loc_code if 0x20 <= ord(c) <= 0x7E)
        logging.debug("The location code of the pci device is %s", loc_code)
        return loc_code
    except FileNotFoundError:
        return "Location code file not found for device %s.", pci_id
    except Exception as e:
        return "An error occurred: %s", e
