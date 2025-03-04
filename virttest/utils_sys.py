"""
Virtualization test utility functions.

:copyright: 2021 Red Hat Inc.
"""

import logging
import re

from avocado.utils import process

from virttest import utils_package, utils_test
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


def update_boot_option(
    vm,
    args_removed="",
    args_added="",
    need_reboot=True,
    guest_arch_name="x86_64",
    serial_login=False,
):
    """
    Update guest default kernel option.

    :param vm: The VM object.
    :param args_removed: Kernel options want to remove.
    :param args_added: Kernel options want to add.
    :param need_reboot: Whether need reboot VM or not.
    :param guest_arch_name: Guest architecture, e.g. x86_64, s390x
    :param serial_login: Login guest via serial session
    :raise exceptions.TestError: Raised if fail to update guest kernel cmdline.

    """
    session = None
    if vm.params.get("os_type") == "windows":
        # this function is only for linux, if we need to change
        # windows guest's boot option, we can use a function like:
        # update_win_bootloader(args_removed, args_added, reboot)
        # (this function is not implement.)
        # here we just:
        msg = "update_boot_option() is supported only for Linux guest"
        LOG.warning(msg)
        return
    login_timeout = int(vm.params.get("login_timeout"))
    session = vm.wait_for_login(
        timeout=login_timeout, serial=serial_login, restart_network=True
    )
    try:
        # check for args that are really required to be added/removed
        req_args, req_remove_args = utils_test.check_kernel_cmdline(
            session, remove_args=args_removed, args=args_added
        )
        if "ubuntu" in vm.get_distro().lower():
            if req_args:
                utils_test.update_boot_option_ubuntu(req_args, session=session)
            if req_remove_args:
                utils_test.update_boot_option_ubuntu(
                    req_remove_args, session=session, remove_args=True
                )
        else:
            if not utils_package.package_install("grubby", session=session):
                raise exceptions.TestError("Failed to install grubby package")
            msg = "Update guest kernel option. "
            cmd = "grubby --update-kernel=`grubby --default-kernel` "
            if req_remove_args:
                msg += " remove args: %s" % req_remove_args
                cmd += '--remove-args="%s" ' % req_remove_args
            if req_args:
                msg += " add args: %s" % req_args
                cmd += '--args="%s"' % req_args
            if req_remove_args or req_args:
                __run_cmd_and_handle_error(
                    msg, cmd, session, "Failed to modify guest kernel option"
                )

        if guest_arch_name == "s390x":
            msg = "Update boot media with zipl"
            cmd = "zipl"
            __run_cmd_and_handle_error(
                msg, cmd, session, "Failed to update boot media with zipl"
            )

        # reboot is required only if we really add/remove any args
        if need_reboot and (req_args or req_remove_args):
            LOG.info("Rebooting guest ...")
            session = vm.reboot(
                session=session, timeout=login_timeout, serial=serial_login
            )
            # check nothing is required to be added/removed by now
            req_args, req_remove_args = utils_test.check_kernel_cmdline(
                session, remove_args=args_removed, args=args_added
            )
            if req_remove_args:
                err = "Fail to remove guest kernel option %s" % args_removed
                raise exceptions.TestError(err)
            if req_args:
                err = "Fail to add guest kernel option %s" % args_added
                raise exceptions.TestError(err)
    finally:
        if session:
            session.close()
