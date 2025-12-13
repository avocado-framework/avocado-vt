"""
Virtualization test utility functions.

:copyright: 2021 Red Hat Inc.
"""

import logging
import re

from avocado.utils import process

from virttest import remote
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


def get_qemu_log(vms, type="local", params=None, log_lines=10):
    """
    Get last N lines of QEMU log from local host and remote host.

    :param vms: VM objects
    :param type: str, valid values: "local", "remote" or "both"
    :param params: dict, test parameters
    :param log_lines: int, number of last lines to retrieve from log, default 10
    :return: list, like [{"vm_name": "vm1", "local": xxx, "remote": xxx}, {"vm_name": "vm2", "local": xxx}]
    """
    logs = []
    if params is not None and type != "local":
        server_ip = params.get("migrate_dest_host", params.get("remote_ip"))
        server_user = params.get("server_user", params.get("remote_user"))
        server_pwd = params.get("server_pwd", params.get("remote_pwd"))
        if server_ip:
            server_session = remote.wait_for_login(
                "ssh", server_ip, "22", server_user, server_pwd, r"[\#\$]\s*$"
            )
        else:
            LOG.warning("Remote host IP not found in params")
    try:
        for vm in vms:
            log_contents = {"vm_name": vm.name}
            log_file = "/var/log/libvirt/qemu/%s.log" % vm.name
            cmd = "tail -n %d %s 2>/dev/null || echo 'Log file not found'" % (
                log_lines,
                log_file,
            )
            if type in ["local", "both"]:
                result = process.run(cmd, shell=True, ignore_status=True, verbose=False)
                log_content = result.stdout_text.strip()
                LOG.debug(
                    "QEMU log from source host for vm %s:\n%s", vm.name, log_content
                )
                log_contents.update({"local": log_content})

            if type in ["remote", "both"] and server_session is not None:
                log_content = server_session.cmd_output(cmd, timeout=10).strip()
                LOG.debug(
                    "QEMU log from remote host for vm %s:\n%s", vm.name, log_content
                )
                log_contents.update({"remote": log_content})
            logs.append(log_contents)

    except Exception as detail:
        LOG.warning("Failed to get QEMU log: %s", detail)
    finally:
        if server_session:
            server_session.close()
    return logs
