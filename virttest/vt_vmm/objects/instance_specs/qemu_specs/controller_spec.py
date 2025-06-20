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

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec
from virttest.vt_vmm.objects.exceptions.instance_exception import InstanceSpecError



LOG = logging.getLogger("avocado." + __name__)


class QemuSpecPCIController(QemuSpec):
    def __init__(self, name, vt_params, node, pcic_name, pcic_params=None):
        super(QemuSpecPCIController, self).__init__(name, vt_params, node)
        self._pcic_name = pcic_name
        self._pcic_params = pcic_params
        self._parse_params()

    def _define_spec(self):
        # Define the PCI controller
        pci_controller = dict()
        if self._pcic_params:
            pcic_params = self._pcic_params.copy()
        else:
            pcic_params = self._params.object_params(self._pcic_name)

        pci_controller["id"] = self._pcic_name
        pci_controller["type"] = pcic_params.get("type", "pcie-root-port")
        if not pcic_params.get("bus"):
            pci_controller["bus"] = pcic_params.get("pci_bus", "pci.0")
        else:
            pci_controller["bus"] = pcic_params.get("bus")
        props = dict()
        props["reserved_slots"] = pcic_params.get("reserved_slots")
        props["multifunction"] = pcic_params.get("multifunction")
        pci_controller["props"] = props

        return pci_controller

    def _parse_params(self):
        self._spec["controllers"] = [self._define_spec()]


class QemuSpecPCIeExtraController(QemuSpec):
    def __init__(self, name, vt_params, node, index):
        super(QemuSpecPCIeExtraController, self).__init__(name, vt_params, node)
        self._index = index
        self._parse_params()

    def _define_spec(self):
        # Define the extra PCIe controllers
        pci_controller = dict()
        pci_controller["id"] = "pcie_extra_root_port_%d" % self._index
        pci_controller["type"] = "pcie-root-port"
        pci_controller["bus"] = "pci.0"

        props = dict()
        pcie_root_port_params = self._params.get("pcie_root_port_params")
        if pcie_root_port_params:
            for extra_param in pcie_root_port_params.split(","):
                key, value = extra_param.split("=")
                props[key] = value

        func_num = self._index % 8
        if func_num == 0:
            props["multifunction"] = "on"

        pci_controller["props"] = props
        return pci_controller

    def _parse_params(self):
        self._spec["controllers"] = [self._define_spec()]


class QemuSpecUSBController(QemuSpec):
    def __init__(self, name, vt_params, node, usb_name):
        super(QemuSpecUSBController, self).__init__(name, vt_params, node)
        self._usb_name = usb_name
        self._parse_params()

    def _define_spec(self):
        # Define USB controller specification

        usb_controller = dict()
        usb_controller_props = dict()
        usb_params = self._params.object_params(self._usb_name)
        usb_type = usb_params.get("usb_type")
        if not self._has_device(usb_type):
            raise InstanceSpecError("Unknown USB: %s" % usb_type)

        usb_controller["id"] = self._usb_name
        usb_controller["type"] = usb_params.get("usb_type")
        usb_controller["bus"] = self._get_pci_bus(usb_params, "usbc", True)
        usb_controller_props["multifunction"] = usb_params.get("multifunction")
        usb_controller_props["masterbus"] = usb_params.get("masterbus")
        usb_controller_props["firstport"] = usb_params.get("firstport")
        usb_controller_props["freq"] = usb_params.get("freq")
        usb_controller_props["max_ports"] = int(usb_params.get("max_ports", 6))
        usb_controller_props["addr"] = usb_params.get("pci_addr")
        usb_controller["props"] = usb_controller_props
        return usb_controller

    def _parse_params(self):
        self._spec["controllers"] = [self._define_spec()]


class QemuSpecControllers(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecControllers, self).__init__(name, vt_params, node)
        self._controllers = []
        self._parse_params()

    def _define_spec(self):
        _qemu_binary = self._params.get("qemu_binary", "qemu")
        if self._has_device("pcie-root-port"):
            root_port_type = "pcie-root-port"
        else:
            root_port_type = "ioh3420"

        if self._has_device("pcie-pci-bridge"):
            pci_bridge_type = "pcie-pci-bridge"
        else:
            pci_bridge_type = "pci-bridge"
        pcie_root_port_params = self._params.get("pcie_root_port_params")
        if "q35" in self._params.get("machine_type"):
            # add default pcie root port plugging pcie device
            port_name = "%s-0" % root_port_type
            port_params = {
                "type": root_port_type,
                # reserve slot 0x0 for plugging in  pci bridge
                "reserved_slots": "0x0",
            }
            if root_port_type == "pcie-root-port":
                port_params["multifunction"] = "on"
            self._controllers.append(QemuSpecPCIController(self._name,
                                                           self._params,
                                                           self._node.tag,
                                                           port_name,
                                                           port_params))

            # add pci bridge for plugging in legacy pci device
            bridge_name = "%s-0" % pci_bridge_type
            bridge_params = {"type": pci_bridge_type, "addr": "0x0", "bus": port_name}
            self._controllers.append(QemuSpecPCIController(self._name,
                                                           self._params,
                                                           self._node.tag,
                                                           bridge_name,
                                                           bridge_params))

        # Define the controllers spec
        for pcic in self._params.objects("pci_controllers"):
            self._controllers.append(QemuSpecPCIController(self._name,
                                                           self._params,
                                                           self._node.tag,
                                                           pcic))
        extra_port_num = int(self._params.get("pcie_extra_root_port", 0))
        for num in range(extra_port_num):
            self._controllers.append(QemuSpecPCIeExtraController(self._name,
                                                                 self._params,
                                                                 self._node.tag,
                                                                 num))
        for usb in self._params.objects("usbs"):
            self._controllers.append(QemuSpecUSBController(self._name,
                                                           self._params,
                                                           self._node.tag,
                                                           usb))

    def insert_spec(self, spec):
        if isinstance(spec, (QemuSpecPCIController,
                             QemuSpecUSBController,
                             QemuSpecPCIeExtraController)):
            self._controllers.append(spec)
            self._spec["controllers"].append(spec.spec["controllers"][0])
        else:
            raise InstanceSpecError("No such specification")

    def remove_spec(self, spec):
        if spec in self._controllers:
            self._controllers.remove(spec)
            self._spec["controllers"].remove(spec["controllers"][0])
        else:
            raise InstanceSpecError("No such spec.")

    def _parse_params(self):
        self._define_spec()
        self._spec["controllers"] = list()
        for ctl_spec in self._controllers:
            self._spec["controllers"].append(ctl_spec.spec["controllers"][0])
