"""
Virtualization test - SwitchDev related utilities

:copyright: Red Hat Inc.
"""
import os
import logging

from avocado.utils import process

from virttest import utils_sriov


LOG = logging.getLogger('avocado.' + __name__)


def unbind_vfs(pf_pci, vf_no=4):
    """
    Unbind VFs

    :param pf_pci: PF's pci, eg. 0000:5e:00.0
    :param vf_no: VFs' numbers
    """
    for idx in range(vf_no):
        pci_addr = utils_sriov.get_vf_pci_id(pf_pci, idx)
        cmd = "echo %s >  /sys/bus/pci/drivers/mlx5_core/unbind" % pci_addr
        process.run(cmd, shell=True)


def set_eswitch_mode(pf_pci, mode="switchdev"):
    """
    Set switch mode

    :param pf_pci: PF's pci, eg. 0000:5e:00.0
    :param mode: The mode
    """
    cmd = "devlink dev eswitch set pci/{}  mode {}".format(pf_pci, mode)
    process.run(cmd, shell=True)


def bind_vfs(pf_pci, vf_no=4):
    """
    Bind VFs

    :param pf_pci: PF's pci, eg. 0000:5e:00.0
    :param vf_no: VFs' numbers
    """
    for idx in range(vf_no):
        pci_addr = utils_sriov.get_vf_pci_id(pf_pci, idx)
        cmd = "echo %s >  /sys/bus/pci/drivers/mlx5_core/bind" % pci_addr
        process.run(cmd, shell=True)


def get_switchid(interface):
    """
    Get switch id

    :param interface: interface name
    :return: switch id
    """
    cmd = "ip -d link show %s | sed -n 's/.* switchid \([^ ]*\).*/\\1/p'" % interface
    return process.run(cmd, shell=True).stdout_text.strip()


def get_all_representors():
    """
    Get all representors from '/sys/class/net' dir

    :return: All representors in '/sys/class/net' dir
    """
    reps = {}
    for ifc in os.listdir('/sys/class/net'):
        try:
            with open(os.path.join('/sys/class/net', ifc, 'phys_port_name'), 'r') as f1:
                port_name = f1.read().strip()
        except OSError:
            pass
        else:
            reps.update({ifc: {'port': port_name}})
        try:
            with open(os.path.join('/sys/class/net', ifc, 'phys_switch_id'), 'r') as f2:
                switch_id = f2.read().strip()
        except OSError:
            pass
        else:
            reps[ifc].update({'switch_id': switch_id})
    return reps


def get_representor(reps, vf_idx, switch_id):
    """
    Get representor by given vf_idx and switch_id

    :param vf_idx: VF's index
    :param switch_id: switch id
    :return: the representor
    """
    for ifc, info in reps.items():
        if info.get('switch_id') == switch_id and \
           info.get('port') == "pf0vf" + str(vf_idx):
            return ifc


def get_rep_list(pf_iface, vf_no=4):
    """
    Get representor list by given pf iface and vf number

    :param pf_iface: PF interface
    :param vf_no: The number of VFs
    :return: A representor list
    """
    rep_list = []
    switchid = get_switchid(pf_iface)
    reps = get_all_representors()
    LOG.debug("Checking switchid %s in %s...", switchid, reps)
    for idx in range(vf_no):
        res = get_representor(reps, idx, switchid)
        if res:
            rep_list.append(res)
    LOG.debug("representor list: %s.", rep_list)
    return rep_list
