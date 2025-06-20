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
# Copyright: Red Hat Inc. 2025 and Avocado contributors
# Authors: Yongxue Hong <yhong@redhat.com>


import logging

from virttest.qemu_devices import qdevices
from virttest.qemu_devices.utils import set_cmdline_format_by_cfg

LOG = logging.getLogger("avocado.service." + __name__)


def create_pci_controller_devices(pci_controller, format_cfg):
    driver = pci_controller.get("type")
    name = pci_controller["id"]
    props = pci_controller.get("props")
    reserved_slots = ""
    if "reserved_slots" in props and props["reserved_slots"] is not None:
        reserved_slots = props["reserved_slots"]
        del props["reserved_slots"]
    pcic_params = {"id": pci_controller["id"]}
    pcic_params.update(props)

    if driver in ("pcie-root-port", "ioh3420", "x3130-upstream", "x3130"):
        bus_type = "PCIE"
    else:
        bus_type = "PCI"
    parent_bus = [{"aobject": pci_controller.get("bus")}]
    if driver == "x3130":
        bus = qdevices.QPCISwitchBus(name, bus_type, "xio3130-downstream", name)
        driver = "x3130-upstream"
    else:
        if driver == "pci-bridge":  # addr 0x01-0x1f, chasis_nr
            parent_bus.append({"busid": "_PCI_CHASSIS_NR"})
            bus_length = 32
            bus_first_port = 1
        elif driver == "i82801b11-bridge":  # addr 0x1-0x13
            bus_length = 20
            bus_first_port = 1
        elif driver in ("pcie-root-port", "ioh3420"):
            bus_length = 1
            bus_first_port = 0
            parent_bus.append({"busid": "_PCI_CHASSIS"})
        elif driver == "pcie-pci-bridge":
            reserved_slots = "0x0"
            # Unsupported PCI slot 0 for standard hotplug controller.
            # Valid slots are between 1 and 31
            bus_length = 32
            bus_first_port = 1
        else:  # addr = 0x0-0x1f
            bus_length = 32
            bus_first_port = 0
        bus = qdevices.QPCIBus(name, bus_type, name, bus_length, bus_first_port)
    for addr in reserved_slots.split():
        bus.reserve(addr)
    dev = qdevices.QDevice(
        driver, pcic_params, aobject=name, parent_bus=parent_bus, child_bus=bus
    )

    set_cmdline_format_by_cfg(dev, format_cfg, "pcic")
    return dev
