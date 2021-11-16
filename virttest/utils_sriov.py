"""
SRIOV related utility functions
"""

import logging
import re
import os

from avocado.core import exceptions

from virttest import utils_misc
from virttest import utils_net
from virttest import utils_package

LOG = logging.getLogger('avocado.' + __name__)


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


def get_pf_info(session=None):
    """
    Get PFs information

    :param session: The session object to the host
    :raise: exceptions.TestError when command fails
    :return: dict, pfs' info.
        eg. {'3b:00.0': {'driver': 'ixgbe', 'pci_id': '0000:3b:00.0',
                         'iface': 'ens1f0', 'status': 'up'},
             '3b:00.1': {'driver': 'ixgbe', 'pci_id': '0000:3b:00.1',
                         'iface': 'ens1f1', 'status': 'down'}}

    """
    pf_info = {}
    status, output = utils_misc.cmd_status_output(
        "lspci |awk '/Ethernet/ {print $1}'", shell=True)
    if status or not output:
        raise exceptions.TestError("Unable to get Ethernet controllers. status: %s,"
                                   "stdout: %s." % (status, output))
    for pci in output.split():
        _, output = utils_misc.cmd_status_output("lspci -v -s %s" % pci,
                                                 shell=True)
        if re.search("SR-IOV", output):
            pf_driver = re.search('driver in use: (.*)', output)[1]
            tmp_info = {'driver': pf_driver, 'pci_id': '0000:%s' % pci}

            iface_name = get_iface_name('0000:%s' % pci, session=session)
            runner = None if not session else session.cmd
            tmp_info.update({'iface': iface_name.strip(),
                             'status': utils_net.get_net_if_operstate(
                                          iface_name.strip(), runner=runner)})
            pf_info.update({pci: tmp_info})
    LOG.debug("PF info: %s.", pf_info)
    return pf_info


def get_pf_pci(session=None):
    """
    Get the pci id of the available(status='up') PF

    :param session: The session object to the host
    :return: pf's pci id, eg. 0000:05:10.1
    """
    pf_info = get_pf_info(session=session)
    for pci_info in pf_info.values():
        if pci_info.get("status", "") == "up":
            return pci_info.get('pci_id')


def get_pf_info_by_pci(pci_id, session=None):
    """
    Get the pci info by the given pci id

    :param pci_id: PF's pci id, eg. 0000:3b:00.0
    :param session: The session object to the host
    :return: Dict, pf's info,
        eg. {'driver': 'ixgbe', 'pci_id': '0000:3b:00.0',
             'iface': 'ens1f0', 'status': 'up'}
    """
    pf_info = get_pf_info(session=session)
    for pf in pf_info.values():
        if pf.get('pci_id') == pci_id:
            LOG.debug("PF %s details: %s.", pci_id, pf)
            return pf


def pci_to_addr(pci_id):
    """
    Get address dict according to pci_id

    :param pci_id: PCI ID of a device(eg. 0000:05:10.1)
    :return: address dict
    """
    pci_list = ["0x%s" % x for x in re.split('[.:]', pci_id)]
    return dict(zip(
        ['domain', 'bus', 'slot', 'function', 'type'], pci_list + ['pci']))


def get_device_name(pci_id):
    """
    Get device name from pci_id

    :param pci_id: PCI ID of a device(eg. 0000:05:10.1)
    :return: Name of a device(eg. pci_0000_05_00_1)
    """
    return '_'.join(['pci']+re.split('[.:]', pci_id))


def get_iface_name(pci_id, session=None):
    """
    Get iface by the given pci

    :param pci_id: PCI ID of a device(eg. 0000:05:10.1)
    :param session: The session object to the host
    :return: The iface(eg. enp5s0f0)
    """
    cmd = "ls /sys/bus/pci/devices/%s/net" % pci_id
    status, iface_name = utils_misc.cmd_status_output(cmd, shell=True,
                                                      session=session)
    if status:
        raise exceptions.TestError("Unable to get iface name of %s." % pci_id)
    return iface_name


def set_vf(pci_addr, vf_no=4, session=None, timeout=60):
    """
    Enable VFs for PF

    :param pci_addr: The pci address
    :param vf_no: The value to be set
    :param session: The session object to the host
    :param timeout: Time limit in seconds to wait for cmd to complete
    :return: True if successful
    """
    LOG.debug("pci_addr is %s", pci_addr)
    cmd = "echo %s > %s/sriov_numvfs" % (vf_no, pci_addr)
    s, o = utils_misc.cmd_status_output(cmd, shell=True, timeout=timeout,
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


def get_vf_mac(ethname, vf_idx=0, session=None, is_admin=True):
    """
    Get mac address for VF via 'ip' command.

    :param ethname: The name of the network interface
    :param vf_idx: The index of VF
    :param session: The session object to the host
    :param is_admin: Whether get admin mac address
    :return: VF's (admin) mac
    """
    if is_admin:
        cmd = "ip link show %s |awk '/vf %d/ {print $4}'" % (ethname, vf_idx)
    else:
        pf_pci = get_pci_from_iface(ethname, session)
        vf_pci = get_vf_pci_id(pf_pci, vf_index=vf_idx, session=session)
        vf_iface = get_iface_name(vf_pci, session=session)
        cmd = "ip link show %s |awk '/link\/ether/ {print $2}'" % vf_iface

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
    cmd = "readlink /sys/bus/pci/devices/{}/virtfn{}".format(pf_pci, vf_index)
    status, tmp_vf = utils_misc.cmd_status_output(
        cmd, shell=True, verbose=True, session=session)
    if status or not tmp_vf:
        raise exceptions.TestError("Unable to get VF. status: %s, stdout: %s."
                                   % (status, tmp_vf))
    return os.path.basename(tmp_vf)


def get_pci_from_iface(iface, session=None):
    """
    Get pci by the given iface

    :param iface: The name of the network interface
    :param session: The session object to the host
    :return: Device's pci(eg. 0000:05:00.0)
    """
    cmd = "ethtool -i %s | awk '/bus-info/ {print $NF}'" % iface.strip()
    status, pci = utils_misc.cmd_status_output(
        cmd, shell=True, verbose=True, session=session)
    if status:
        raise exceptions.TestError("Unable to get device's pci. status: %s, "
                                   "stdout: %s." % (status, pci))
    return pci


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
        LOG.error("Failed to install the required package")
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
