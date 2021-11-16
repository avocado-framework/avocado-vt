"""
Virtualization test - vDPA related utilities

:copyright: Red Hat Inc.
"""
import logging
import time

from avocado.core import exceptions
from avocado.utils import process

from virttest import openvswitch
from virttest import utils_misc
from virttest import utils_sriov
from virttest import utils_switchdev
from virttest.utils_kernel_module import KernelModuleHandler
from virttest.versionable_class import factory

LOG = logging.getLogger('avocado.' + __name__)


class VDPAOvsTest(object):
    """
    Wrapper class for vDPA OVS environment configuration
    """
    def __init__(self, pf_pci, vf_no=4):
        self.pf_pci = pf_pci
        self.vf_no = vf_no
        self.pf_pci_path = utils_misc.get_pci_path(self.pf_pci)
        utils_sriov.set_vf(self.pf_pci_path, 0)

        self.pf_iface = utils_sriov.get_pf_info_by_pci(self.pf_pci).get('iface')
        if not self.pf_iface:
            raise exceptions.TestCancel("NO available pf found.")
        self.br_name = self.pf_iface+'_br'

        self.ovs = factory(openvswitch.OpenVSwitchSystem)()

    def __del__(self):
        self.cleanup()

    def load_modules(self):
        """
        Load modules
        """
        modules = ['vdpa', 'vhost_vdpa', 'mlx5_vdpa']
        for module_name in modules:
            KernelModuleHandler(module_name).reload_module(True)

    def unload_modules(self):
        """
        Unload modules
        """
        modules = ['mlx5_vdpa', 'vhost_vdpa', 'vdpa']
        for module_name in modules:
            KernelModuleHandler(module_name).unload_module()

    def config_vdpa_dev(self):
        """
        Bind VFs and add vDPA dev

        :raise: TestError if vf device is not found
        """
        utils_switchdev.bind_vfs(self.pf_pci, self.vf_no)
        for idx in range(self.vf_no):
            vf_pci = utils_sriov.get_vf_pci_id(self.pf_pci, vf_index=idx)
            vf_dev = utils_sriov.get_iface_name(vf_pci)
            if not vf_dev:
                raise exceptions.TestError("Cannot get VF network device!")
            self.set_tc_offload(vf_dev)
            self.set_dev_managed_no(vf_dev)
            self.add_vdpa_dev(idx, vf_pci)

    def get_rep_list(self):
        """
        Get representor list

        :return: representor list
        """
        return utils_switchdev.get_rep_list(self.pf_iface, self.vf_no)

    def config_reps(self):
        """
        Configure reps
        """
        for rep in self.get_rep_list():
            self.set_tc_offload(rep)
            self.set_dev_managed_no(rep)
            self.set_ifc_up(rep)

    def add_vdpa_dev(self, idx, pci_addr):
        """
        Add vDPA device

        :param idx: Index of dev
        :param pci_addr: PCI address
        """
        cmd = "vdpa dev add name vdpa{} mgmtdev pci/{}".format(idx, pci_addr)
        process.run(cmd, shell=True)

    def set_dev_managed_no(self, dev):
        """
        Set 'managed' to 'no' for device

        :param dev: device
        """
        cmd = "nmcli device set %s managed no" % dev
        process.run(cmd, shell=True)

    def set_tc_offload(self, dev):
        """
        Enable tc-offload

        :param dev: device
        """
        cmd = "ethtool -K %s hw-tc-offload on" % dev
        process.run(cmd, shell=True)

    def set_ifc_up(self, dev):
        """
        Set interface up

        :param dev: device
        """
        cmd = "ip link set %s up" % dev
        process.run(cmd, shell=True)

    def set_switchdev_mode(self):
        """
        Set switchdev_mode
        """
        self.set_dev_managed_no(self.pf_iface)
        self.set_tc_offload(self.pf_iface)
        self.config_vdpa_dev()

    def create_ovs_ports(self):
        """
        Create ovs ports
        """
        self.ovs.add_br(self.br_name)
        self.ovs.add_port(self.br_name, self.pf_iface)
        for rep in self.get_rep_list():
            self.ovs.add_port(self.br_name, rep)

    def del_ovs_br(self):
        """
        Delete ovs bridge
        """
        for brname in self.ovs.list_br():
            self.ovs.del_br(brname)

    def setup(self):
        """
        Setup vDPA environment
        """
        LOG.debug("Loading vDPA Kernel modules...")
        self.load_modules()
        self.ovs.init_system()
        LOG.debug("Enabling OVS HW Offload...")
        self.ovs.ovs_vsctl(['set', 'Open_vSwitch', '.', 'other_config:hw-offload="true"'])
        LOG.debug("Delete OVS Bridges.")
        self.del_ovs_br()

        LOG.debug("Creating VFs...")
        utils_sriov.set_vf(self.pf_pci_path, self.vf_no)
        LOG.debug("Unbinding VFs...")
        utils_switchdev.unbind_vfs(self.pf_pci, self.vf_no)

        LOG.debug("Setting switchdev mode...")
        utils_switchdev.set_eswitch_mode(self.pf_pci)
        # Wait for 5 secs
        time.sleep(5)
        self.set_switchdev_mode()
        LOG.debug("Configuring representors...")
        self.config_reps()
        LOG.debug("Setting PF link up...")
        self.set_ifc_up(self.pf_iface)

        LOG.debug("Create OVS bridge and ports.")
        self.create_ovs_ports()
        LOG.info("vDPA environment setup successfully.")

    def cleanup(self):
        """
        Clean up vDPA environment
        """
        utils_sriov.set_vf(self.pf_pci_path, 0)
        self.del_ovs_br()
        self.unload_modules()
        LOG.debug("vDPA environment recover successfully.")


class VDPASimulatorTest(object):

    def __init__(self, sim_dev_module='vdpa_sim_net'):
        self.sim_dev_module = sim_dev_module

    def __del__(self):
        self.cleanup()

    def load_modules(self):
        """
        Load modules
        """
        self.unload_modules()
        modules = ['vdpa', 'vhost_vdpa', 'vdpa_sim', self.sim_dev_module]
        for module_name in modules:
            KernelModuleHandler(module_name).reload_module(True)

    def unload_modules(self):
        """
        Unload modules
        """
        modules = [self.sim_dev_module, 'vdpa_sim', 'vhost_vdpa', 'vdpa']
        for module_name in modules:
            KernelModuleHandler(module_name).unload_module()

    def add_vdpa_dev(self, idx=0, dev="vdpasim_net"):
        """
        Add vDPA device

        :param idx: Index of dev
        :param dev: device name
        """
        cmd = "vdpa dev add name vdpa{} mgmtdev {}".format(idx, dev)
        process.run(cmd, shell=True)

    def setup(self):
        """
        Setup vDPA Simulator environment
        """
        LOG.debug("Loading vDPA Kernel modules...")
        self.load_modules()
        LOG.debug("Adding vDPA device...")
        self.add_vdpa_dev()
        LOG.info("vDPA Simulator environment setup successfully.")

    def cleanup(self):
        """
        Cleanup vDPA Simulator environment
        """
        self.unload_modules()
        LOG.info("vDPA Simulator environment recover successfully.")


def get_vdpa_pci(driver='mlx5_core'):
    """
    Get PF's pci id by given driver

    :param driver: The driver name
    :return: pf's pci id, eg. 0000:5e:00.0
    """
    pf_info = utils_sriov.get_pf_info()
    for pci_info in pf_info.values():
        if pci_info.get("driver", "") == driver:
            return pci_info.get('pci_id')
