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


def set_vf_mac(ethname, mac_addr, vf_idx=0, session=None):
    """
    Set mac address for VF

    :param ethname: The name of the network interface
    :param mac_addr: The mac address to be set
    :param vf_idx: The index of VF
    :param session: The session object to the host
    :return: The command status and output
    """
    cmd = "ip link set {0} vf {1} mac {2}".format(ethname, vf_idx, mac_addr)
    return utils_misc.cmd_status_output(
            cmd, shell=True, verbose=True, session=session)


def get_vf_mac(ethname, vf_idx=0, session=None):
    """
    Get admin mac address for VF via 'ip' command.

    :param ethname: The name of the network interface
    :param vf_idx: The index of VF
    :param session: The session object to the host
    :return: VF's admin mac
    """
    cmd = "ip link show %s |awk '/vf %d/ {print $4}'" % (ethname, vf_idx)
    status, vf_mac = utils_misc.cmd_status_output(
            cmd, shell=True, verbose=True, session=session)

    if status or not vf_mac:
        raise exceptions.TestError("Unable to get VF's mac address. status: %s,"
                                   "stdout: %s." % (status, vf_mac))
    return vf_mac.strip()


def get_vf_pci_id(pf_pci, vf_index=0, session=None):
    """
    Get pci_id of VF

    :param pf_pci: The pci id of PF
    :param vf_index: VF's index
    :param session: The session object to the host
    :return: VF's pci id
    """
    cmd = "ls /sys/bus/pci/devices/{}/virtfn{}/net".format(pf_pci, vf_index)
    status, vf_name = utils_misc.cmd_status_output(
        cmd, shell=True, verbose=True, session=session)
    if status or not vf_name:
        raise exceptions.TestError("Unable to get VF. status: %s, stdout: %s."
                                   % (status, vf_name))
    cmd = "ethtool -i %s | awk '/bus-info/ {print $NF}'" % vf_name.strip()
    status, vf_pci = utils_misc.cmd_status_output(
        cmd, shell=True, verbose=True, session=session)
    if status:
        raise exceptions.TestError("Unable to get VF's pci. status: %s, "
                                   "stdout: %s." % (status, vf_pci))
    return vf_pci


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

    if not utils_package.package_install(["tmux", "dhcp-client"], session):
        logging.error("Failed to install the required package")
    recover_cmd = 'tmux -c "ip link set {0} nomaster; ip link delete {1}; ' \
                  'pkill dhclient; sleep 5; dhclient"'.format(
                      pf_name, bridge_name)

    if not is_del:
        utils_misc.cmd_status_output(recover_cmd, shell=True, session=session)
        cmd = 'tmux -c "ip link add name {1} type bridge; ip link set {0} up; ' \
              'ip link set {0} master {1}; ip link set {1} up; dhclient -r;' \
              'sleep 5; dhclient"'.format(pf_name, bridge_name)
    else:
        cmd = recover_cmd

    utils_misc.cmd_status_output(cmd, shell=True, verbose=True,
                                 ignore_status=False, session=session)
