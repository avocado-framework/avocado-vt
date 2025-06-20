# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>


import logging
import six
import re

from virttest.qemu_capabilities import Flags
from virttest.utils_version import VersionInterval

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ....objects import instance_spec

LOG = logging.getLogger("avocado." + __name__)


# FIXME: To keep the consistency for the previous version
class CpuInfo(object):

    """
    A class for VM's cpu information.
    """

    def __init__(
        self,
        model=None,
        vendor=None,
        flags=None,
        family=None,
        qemu_type=None,
        smp=0,
        maxcpus=0,
        cores=0,
        threads=0,
        dies=0,
        clusters=0,
        sockets=0,
        drawers=0,
        books=0,
    ):
        """
        :param model: CPU Model of VM (use 'qemu -cpu ?' for list)
        :param vendor: CPU Vendor of VM
        :param flags: CPU Flags of VM
        :param family: CPU Family of VM
        :param qemu_type: cpu driver type of qemu
        :param smp: set the number of CPUs to 'n' [default=1]
        :param maxcpus: maximum number of total cpus, including
                        offline CPUs for hotplug, etc
        :param cores: number of CPU cores on one socket (for PC, it's on one die)
        :param threads: number of threads on one CPU core
        :param dies: number of CPU dies on one socket (for PC only)
        :param clusters: number of CPU clusters on one socket (for ARM only)
        :param sockets: number of discrete sockets in the system
        :param drawers: number of discrete drawers in the system (for s390x only)
        :param books: number of discrete books in the system (for s390x only)
        """
        self.model = model
        self.vendor = vendor
        self.flags = flags
        self.family = family
        self.qemu_type = qemu_type
        self.smp = smp
        self.maxcpus = maxcpus
        self.cores = cores
        self.threads = threads
        self.dies = dies
        self.clusters = clusters
        self.sockets = sockets
        self.drawers = drawers
        self.books = books


class QemuSpec(instance_spec.Spec):

    cache_map = {
        "writeback": {
            "write-cache": "on",
            "cache.direct": "off",
            "cache.no-flush": "off",
        },
        "none": {"write-cache": "on", "cache.direct": "on", "cache.no-flush": "off"},
        "writethrough": {
            "write-cache": "off",
            "cache.direct": "off",
            "cache.no-flush": "off",
        },
        "directsync": {
            "write-cache": "off",
            "cache.direct": "on",
            "cache.no-flush": "off",
        },
        "unsafe": {"write-cache": "on", "cache.direct": "off", "cache.no-flush": "on"},
    }

    BLOCKDEV_VERSION_SCOPE = "[2.12.0, )"
    SMP_DIES_VERSION_SCOPE = "[4.1.0, )"
    SMP_CLUSTERS_VERSION_SCOPE = "[7.0.0, )"
    SMP_BOOKS_VERSION_SCOPE = "[8.2.0, )"
    SMP_DRAWERS_VERSION_SCOPE = "[8.2.0, )"
    FLOPPY_DEVICE_VERSION_SCOPE = "[5.1.0, )"
    BLOCKJOB_BACKING_MASK_PROTOCOL_VERSION_SCOPE = "[9.0.0, )"

    def __init__(self, vm_name, vm_params, node):
        super(QemuSpec, self).__init__(vm_name, vm_params, node)
        self._specs = [] # the list of the sub specs
        self._qemu_binary = self._params.get("qemu_binary", "qemu")
        self._qemu_machines_info = self._node.proxy.virt.tools.qemu.get_machines_info(self._qemu_binary)
        self._qemu_ver = self._node.proxy.virt.tools.qemu.get_version(self._qemu_binary)[0]
        self._qemu_help = self._node.proxy.virt.tools.qemu.get_help_info(None, self._qemu_binary)
        self._qemu_caps = set()
        self._cpuinfo = CpuInfo()
        self._probe_capabilities()
        self._index_in_use = {}

        self._last_driver_index = 0
        self._last_boot_index = 0

        # init the dict index_in_use
        for key in list(self._params.keys()):
            if "drive_index" in key:
                self._index_in_use[self._params.get(key)] = True

    def insert_spec(self, spec):
        if isinstance(spec, QemuSpec):
            self._specs.append(spec)
        else:
            raise ValueError("No support this type of specification")

    def remove_spec(self, spec):
        for _spec in self._specs[::]:
            if _spec == spec:
                self._specs.remove(_spec)
                break
        else:
            raise ValueError("No such specification")

    def _none_or_int(self, value):
        """ Helper function which returns None or int() """
        if isinstance(value, int):
            return value
        elif not value:  # "", None, False
            return None
        elif isinstance(value, six.string_types) and value.isdigit():
            return int(value)
        else:
            raise TypeError("This parameter has to be int or none")

    def _probe_capabilities(self):
        """Probe capabilities."""
        # -blockdev
        if self._has_option("blockdev") and self._qemu_ver in VersionInterval(
            self.BLOCKDEV_VERSION_SCOPE
        ):
            self._qemu_caps.add(Flags.BLOCKDEV)
        # -smp dies=?
        if self._qemu_ver in VersionInterval(self.SMP_DIES_VERSION_SCOPE):
            self._qemu_caps.add(Flags.SMP_DIES)
        # -smp clusters=?
        if self._qemu_ver in VersionInterval(self.SMP_CLUSTERS_VERSION_SCOPE):
            self._qemu_caps.add(Flags.SMP_CLUSTERS)
        # -smp drawers=?
        if self._qemu_ver in VersionInterval(self.SMP_DRAWERS_VERSION_SCOPE):
            self._qemu_caps.add(Flags.SMP_DRAWERS)
        # -smp book=?
        if self._qemu_ver in VersionInterval(self.SMP_BOOKS_VERSION_SCOPE):
            self._qemu_caps.add(Flags.SMP_BOOKS)
        # -incoming defer
        if self._has_option("incoming defer"):
            self._qemu_caps.add(Flags.INCOMING_DEFER)
        # -machine memory-backend
        machine_help = self._node.proxy.virt.tools.qemu.get_help_info(
            "-machine none,", self._qemu_binary)
        if re.search(r"memory-backend=", machine_help, re.MULTILINE):
            self._qemu_caps.add(Flags.MACHINE_MEMORY_BACKEND)
        # -object sev-guest
        if self._has_object("sev-guest"):
            self._qemu_caps.add(Flags.SEV_GUEST)
        # -object tdx-guest
        if self._has_object("tdx-guest"):
            self._qemu_caps.add(Flags.TDX_GUEST)
        # -device floppy,drive=$drive
        if self._qemu_ver in VersionInterval(self.FLOPPY_DEVICE_VERSION_SCOPE):
            self._qemu_caps.add(Flags.FLOPPY_DEVICE)
        if self._qemu_ver in VersionInterval(
            self.BLOCKJOB_BACKING_MASK_PROTOCOL_VERSION_SCOPE
        ):
            self._qemu_caps.add(Flags.BLOCKJOB_BACKING_MASK_PROTOCOL)

    def _has_option(self, name):
        return self._node.proxy.virt.tools.qemu.has_option(name, self._qemu_binary)

    def _has_device(self, device):
        """
        :param device: Desired device
        :return: Is the desired device supported by current qemu?
        """
        return self._node.proxy.virt.tools.qemu.has_device(device, self._qemu_binary)

    def _has_object(self, obj):
        """
        :param obj: Desired object string, e.g. 'sev-guest'
        :return: True if the object is supported by qemu, or False
        """
        return self._node.proxy.virt.tools.qemu.has_object(obj, self._qemu_binary)

    def _is_pci_device(self, device):
        return self._node.proxy.virt.tools.qemu.is_pci_device(device, self._qemu_binary)

    def _get_bus(self, params, dtype=None, pcie=False):
        """
        Deal with different buses for multi-arch
        """
        if params.get("machine_type").startswith("s390"):
            return self._get_ccw_bus()
        else:
            return self._get_pci_bus(params, dtype, pcie)

    @staticmethod
    def _get_ccw_bus():
        """
        Get device parent bus for s390x
        """
        return "virtual-css"

    def _get_pci_bus(self, params, dtype=None, pcie=False):
        """
        Get device parent pci bus by dtype

        :param params: test params for the device
        :param dtype: device type like, 'nic', 'disk',
                      'vio_rng', 'vio_port' or 'cdrom'
        :param pcie: it's a pcie device or not (bool type)

        :return: return bus
        """
        machine_type = params.get("machine_type", "")
        if "mmio" in machine_type:
            return None
        if dtype and "%s_pci_bus" % dtype in params:
            return params["%s_pci_bus" % dtype]
        if machine_type == "q35" and not pcie:
            # for legacy pic device(eg. rtl8139, e1000)
            if self._has_device("pcie-pci-bridge"):
                bridge_type = "pcie-pci-bridge"
            else:
                bridge_type = "pci-bridge"
            return "%s-0" % bridge_type
        return params.get("pci_bus", "pci.0")

    def _get_index(self, index):
        while self._index_in_use.get(str(index)):
            index += 1
        return index
