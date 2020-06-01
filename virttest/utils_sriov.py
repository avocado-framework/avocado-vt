"""
SRIOV related utility functions
"""

import logging

from avocado.core import exceptions

from virttest import utils_misc
from virttest import utils_net
from virttest import utils_package


def find_pf(driver, session=None):
    """
    Check if available PF exists to test

    :param driver: The driver name, for example "ixgbe"
    :param session: The session object to the host
    :raise: exceptions.TestError when no pf found
    :return: (interface name, pf device)
    """
    driver_dir = "/sys/bus/pci/drivers/%s" % driver
    cmd = "ls -d %s/000*" % driver_dir
    s_, output = utils_misc.cmd_status_output(cmd, shell=True,
                                              ignore_status=False,
                                              session=session)
    runner = None
    if session:
        runner = session.cmd
    pf_tmp = ()
    pf_devices = output.splitlines()
    for pf in pf_devices:
        cmd = "ls %s/net" % pf
        s_, tpm_iface_name = utils_misc.cmd_status_output(cmd, shell=True,
                                                          ignore_status=False,
                                                          session=session)

        if (utils_net.get_net_if_operstate(
           tpm_iface_name.strip(), runner=runner) == "up"):
            pf_tmp = (tpm_iface_name.strip(), pf.strip().split('/')[-1])
            break

    if not pf_tmp:
        raise exceptions.TestError("NO available pf found.")
    return pf_tmp


def set_vf(pci_addr, vf_no=4, session=None):
    """
    Enable VFs for PF

    :param pci_addr: The pci address
    :param vf_no: The value to be set
    :param session: The session object to the host
    :return: True if successful
    """
    logging.debug("pci_addr is %s", pci_addr)
    cmd = "echo %s > %s/sriov_numvfs" % (vf_no, pci_addr)
    s, o = utils_misc.cmd_status_output(cmd, shell=True,
                                        verbose=True, session=session)
    return not s


def add_or_del_connection(params, session=None, is_del=False):
    """
    Add/Delete connections

    :param params: the parameters dict
    :param session: The session object to the host
    :param is_del: Whether the connection should be deleted
    """
    bridge_name = params.get("bridge_name")
    pf_name = params.get("pf_name")

    if not all([bridge_name, pf_name]):
        return

    if not utils_package.package_install(["tmux"], session):
        logging.error("Failed to install required package - tmux!")
    recover_cmd = 'tmux -c "ip link set {0} nomaster; ip link delete {1}; ' \
                  'pkill dhclient; sleep 5; dhclient {0}"'.format(pf_name,
                                                                  bridge_name)

    if not is_del:
        utils_misc.cmd_status_output(recover_cmd, shell=True, session=session)
        cmd = 'tmux -c "ip link add name {1} type bridge; ip link set {0} up; ' \
              'ip link set {0} master {1}; ip link set {1} up; dhclient -r;' \
              'sleep 5; dhclient {1}"'.format(pf_name, bridge_name)
    else:
        cmd = recover_cmd

    utils_misc.cmd_status_output(cmd, shell=True, verbose=True,
                                 ignore_status=False, session=session)
