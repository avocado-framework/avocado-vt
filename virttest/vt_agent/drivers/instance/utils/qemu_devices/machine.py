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
from vt_agent.core import data_dir as core_data_dir

LOG = logging.getLogger("avocado.service." + __name__)


def create_machine_q35(machine_props, cpu, controller, has_option_device, has_option_global):
    """
    Q35 + ICH9
    """
    devices = []
    pcie_root_port_params = None
    cpu_model = None
    if cpu["info"]["model"]:
        cpu_model = cpu["info"]["model"]
    root_port_type = controller.get("type")
    controller_props = controller.get("props")
    if controller_props:
        pcie_root_port_params = controller_props.get("root_port_props")
    bus = (
        qdevices.QPCIEBus(
            "pcie.0", "PCIE", root_port_type, "pci.0",
            pcie_root_port_params
        ),
        qdevices.QStrictCustomBus(
            None, [["chassis"], [256]], "_PCI_CHASSIS", first_port=[1]
        ),
        qdevices.QStrictCustomBus(
            None, [["chassis_nr"], [256]], "_PCI_CHASSIS_NR",
            first_port=[1]
        ),
        qdevices.QCPUBus(cpu_model, [[""], [0]], "vcpu"),
    )
    # pflash_devices = pflash_handler("ovmf", machine_params)
    # devices.extend(pflash_devices)
    # FIXME: hard code workaround to add pflash related devices infiormation
    machine_props["pflash0"] = "drive_ovmf_code"
    machine_props["pflash1"] = "drive_ovmf_vars"
    devices.append(
        qdevices.QMachine(params=machine_props, child_bus=bus,
                          aobject="pci.0")
    )
    devices.append(
        qdevices.QStringDevice(
            "mch", {"addr": 0, "driver": "mch"},
            parent_bus={"aobject": "pci.0"}
        )
    )
    devices.append(
        qdevices.QStringDevice(
            "ICH9-LPC",
            {"addr": "1f.0", "driver": "ICH9-LPC"},
            parent_bus={"aobject": "pci.0"},
        )
    )
    devices.append(
        qdevices.QStringDevice(
            "ICH9 SMB",
            {"addr": "1f.3", "driver": "ICH9 SMB"},
            parent_bus={"aobject": "pci.0"},
        )
    )
    devices.append(
        qdevices.QStringDevice(
            "ICH9-ahci",
            {"addr": "1f.2", "driver": "ich9-ahci"},
            parent_bus={"aobject": "pci.0"},
            child_bus=qdevices.QAHCIBus("ide"),
        )
    )
    if has_option_device and has_option_global:
        devices.append(
            qdevices.QStringDevice(
                "fdc", child_bus=qdevices.QFloppyBus("floppy")
            )
        )
    else:
        devices.append(
            qdevices.QStringDevice(
                "fdc", child_bus=qdevices.QOldFloppyBus("floppy")
            )
        )

    return devices


def create_machine_i440fx(machine_props, cpu, has_option_device, has_option_global):
    """
    i440FX + PIIX
    """
    devices = []
    pci_bus = "pci.0"
    cpu_model = None
    if cpu["info"]["model"]:
        cpu_model = cpu["info"]["model"]

    bus = (
        qdevices.QPCIBus(pci_bus, "PCI", "pci.0"),
        qdevices.QStrictCustomBus(
            None, [["chassis"], [256]], "_PCI_CHASSIS", first_port=[1]
        ),
        qdevices.QStrictCustomBus(
            None, [["chassis_nr"], [256]], "_PCI_CHASSIS_NR",
            first_port=[1]
        ),
        qdevices.QCPUBus(cpu_model, [[""], [0]], "vcpu"),
    )
    # TODO: support pflash devices
    # pflash_devices = pflash_handler("ovmf", machine_params)
    # devices.extend(pflash_devices)
    devices.append(
        qdevices.QMachine(params=machine_props, child_bus=bus,
                          aobject="pci.0")
    )
    devices.append(
        qdevices.QStringDevice(
            "i440FX",
            {"addr": 0, "driver": "i440FX"},
            parent_bus={"aobject": "pci.0"},
        )
    )
    devices.append(
        qdevices.QStringDevice(
            "PIIX4_PM",
            {"addr": "01.3", "driver": "PIIX4_PM"},
            parent_bus={"aobject": "pci.0"},
        )
    )
    devices.append(
        qdevices.QStringDevice(
            "PIIX3",
            {"addr": 1, "driver": "PIIX3"},
            parent_bus={"aobject": "pci.0"},
        )
    )
    devices.append(
        qdevices.QStringDevice(
            "piix3-ide",
            {"addr": "01.1", "driver": "piix3-ide"},
            parent_bus={"aobject": "pci.0"},
            child_bus=qdevices.QIDEBus("ide"),
        )
    )
    if has_option_device and has_option_global:
        devices.append(
            qdevices.QStringDevice(
                "fdc", child_bus=qdevices.QFloppyBus("floppy")
            )
        )
    else:
        devices.append(
            qdevices.QStringDevice(
                "fdc", child_bus=qdevices.QOldFloppyBus("floppy")
            )
        )
    return devices


def create_machine_pseries(machine_props, cpu, has_option_device, has_option_global):
    """
     Pseries, not full support yet.
     """
    # TODO: This one is copied from machine_i440FX, in order to
    #  distinguish it from the i440FX, its bus structure will be
    #  modified in the future.
    devices = []
    cpu_model = None
    if cpu["info"]["model"]:
        cpu_model = cpu["info"]["model"]
    pci_bus = "pci.0"
    bus = (
        qdevices.QPCIBus(pci_bus, "PCI", "pci.0"),
        qdevices.QStrictCustomBus(
            None, [["chassis"], [256]], "_PCI_CHASSIS", first_port=[1]
        ),
        qdevices.QStrictCustomBus(
            None, [["chassis_nr"], [256]], "_PCI_CHASSIS_NR",
            first_port=[1]
        ),
        qdevices.QCPUBus(cpu_model, [[""], [0]], "vcpu"),
    )
    devices.append(
        qdevices.QMachine(params=machine_props, child_bus=bus,
                          aobject="pci.0")
    )
    devices.append(
        qdevices.QStringDevice(
            "i440FX",
            {"addr": 0, "driver": "i440FX"},
            parent_bus={"aobject": "pci.0"},
        )
    )
    devices.append(
        qdevices.QStringDevice(
            "PIIX4_PM",
            {"addr": "01.3", "driver": "PIIX4_PM"},
            parent_bus={"aobject": "pci.0"},
        )
    )
    devices.append(
        qdevices.QStringDevice(
            "PIIX3",
            {"addr": 1, "driver": "PIIX3"},
            parent_bus={"aobject": "pci.0"},
        )
    )
    devices.append(
        qdevices.QStringDevice(
            "piix3-ide",
            {"addr": "01.1", "driver": "piix3-ide"},
            parent_bus={"aobject": "pci.0"},
            child_bus=qdevices.QIDEBus("ide"),
        )
    )
    if has_option_device and has_option_global:
        devices.append(
            qdevices.QStringDevice(
                "fdc", child_bus=qdevices.QFloppyBus("floppy")
            )
        )
    else:
        devices.append(
            qdevices.QStringDevice(
                "fdc", child_bus=qdevices.QOldFloppyBus("floppy")
            )
        )
    return devices

def create_machine_s390_virtio(machine_props, cpu):
    """
    s390x (s390) doesn't support PCI bus.
    """
    devices = []
    cpu_model = None
    if cpu["info"]["model"]:
        cpu_model = cpu["info"]["model"]
    # Add virtio-bus
    # TODO: Currently this uses QNoAddrCustomBus and does not
    # set the device's properties. This means that the qemu qtree
    # and autotest's representations are completely different and
    # can't be used.
    LOG.warn("Support for s390x is highly experimental!")
    bus = (
        qdevices.QNoAddrCustomBus(
            "bus",
            [["addr"], [64]],
            "virtio-blk-ccw",
            "virtio-bus",
            "virtio-blk-ccw",
        ),
        qdevices.QNoAddrCustomBus(
            "bus", [["addr"], [32]], "virtual-css", "virtual-css",
            "virtual-css"
        ),
        qdevices.QCPUBus(cpu_model, [[""], [0]], "vcpu"),
    )
    devices.append(
        qdevices.QMachine(
            params=machine_props, child_bus=bus, aobject="virtio-blk-ccw"
        )
    )
    return devices

def create_machine_arm64_pci(machine_props, controller):
    """
    Experimental support for pci-based aarch64
    """
    LOG.warn("Support for aarch64 is highly experimental!")
    devices = []

    root_port_type = controller.get("type")
    controller_props = controller.get("props")
    if controller_props:
        pcie_root_port_params = controller_props.get("root_port_props")

    bus = (
        qdevices.QPCIEBus(
            "pcie.0", "PCIE", root_port_type, "pci.0",
            pcie_root_port_params
        ),
        qdevices.QStrictCustomBus(
            None, [["chassis"], [256]], "_PCI_CHASSIS", first_port=[1]
        ),
        qdevices.QStrictCustomBus(
            None, [["chassis_nr"], [256]], "_PCI_CHASSIS_NR",
            first_port=[1]
        ),
    )
    # pflash_devices = pflash_handler("aavmf", machine_params)
    # devices.extend(pflash_devices)
    devices.append(
        qdevices.QMachine(params=machine_props, child_bus=bus,
                          aobject="pci.0")
    )
    devices.append(
        qdevices.QStringDevice(
            "gpex-root",
            {"addr": 0, "driver": "gpex-root"},
            parent_bus={"aobject": "pci.0"},
        )
    )

    return devices

def create_machine_arm64_mmio(machine_props):
    """
    aarch64 (arm64) doesn't support PCI bus, only MMIO transports.
    Also it requires pflash for EFI boot.
    """
    LOG.warn("Support for aarch64 is highly experimental!")
    devices = []
    # Add virtio-bus
    # TODO: Currently this uses QNoAddrCustomBus and does not
    # set the device's properties. This means that the qemu qtree
    # and autotest's representations are completely different and
    # can't be used.
    bus = qdevices.QNoAddrCustomBus(
        "bus",
        [["addr"], [32]],
        "virtio-mmio-bus",
        "virtio-bus",
        "virtio-mmio-bus",
    )
    # pflash_devices = pflash_handler("aavmf", machine_params)
    # devices.extend(pflash_devices)
    devices.append(
        qdevices.QMachine(
            params=machine_props, child_bus=bus, aobject="virtio-mmio-bus"
        )
    )
    return devices

def create_machine_riscv64_mmio(machine_props):
    """
    riscv doesn't support PCI bus, only MMIO transports.
    """
    LOG.warn(
        "Support for riscv64 is highly experimental. See "
        "https://avocado-vt.readthedocs.io"
        "/en/latest/Experimental.html#riscv64 for "
        "setup information."
    )
    devices = []
    # Add virtio-bus
    # TODO: Currently this uses QNoAddrCustomBus and does not
    # set the device's properties. This means that the qemu qtree
    # and autotest's representations are completely different and
    # can't be used.
    bus = qdevices.QNoAddrCustomBus(
        "bus",
        [["addr"], [32]],
        "virtio-mmio-bus",
        "virtio-bus",
        "virtio-mmio-bus",
    )
    devices.append(
        qdevices.QMachine(
            params=machine_props, child_bus=bus, aobject="virtio-mmio-bus"
        )
    )
    return devices

def create_machine_other(machine_props):
    """
    isapc or unknown machine type. This type doesn't add any default
    buses or devices, only sets the cmdline.
    """
    LOG.warn(
        "Machine type isa/unknown is not supported by "
        "avocado-vt. False errors might occur"
    )
    devices = [qdevices.QMachine(params=machine_props)]
    return devices


def create_machine_devices(machine, cpu, controller, has_option_device, has_option_global):
    # def create_pcic(name, params, parent_bus=None):
    #     """
    #     Creates pci controller/switch/... based on params
    #
    #     :param name: Autotest name
    #     :param params: PCI controller params
    #     :note: x3130 creates x3130-upstream bus + xio3130-downstream port for
    #            each inserted device.
    #     :warning: x3130-upstream device creates only x3130-upstream device
    #               and you are responsible for creating the downstream ports.
    #     """
    #     driver = params.get("type", "pcie-root-port")
    #     pcic_params = {"id": name}
    #     if driver in ("pcie-root-port", "ioh3420", "x3130-upstream", "x3130"):
    #         bus_type = "PCIE"
    #     else:
    #         bus_type = "PCI"
    #     if not parent_bus:
    #         parent_bus = [{"aobject": params.get("pci_bus", "pci.0")}]
    #     elif not isinstance(parent_bus, (list, tuple)):
    #         parent_bus = [parent_bus]
    #     if driver == "x3130":
    #         bus = qdevices.QPCISwitchBus(name, bus_type, "xio3130-downstream", name)
    #         driver = "x3130-upstream"
    #     else:
    #         if driver == "pci-bridge":  # addr 0x01-0x1f, chasis_nr
    #             parent_bus.append({"busid": "_PCI_CHASSIS_NR"})
    #             bus_length = 32
    #             bus_first_port = 1
    #         elif driver == "i82801b11-bridge":  # addr 0x1-0x13
    #             bus_length = 20
    #             bus_first_port = 1
    #         elif driver in ("pcie-root-port", "ioh3420"):
    #             bus_length = 1
    #             bus_first_port = 0
    #             parent_bus.append({"busid": "_PCI_CHASSIS"})
    #         elif driver == "pcie-pci-bridge":
    #             params["reserved_slots"] = "0x0"
    #             # Unsupported PCI slot 0 for standard hotplug controller.
    #             # Valid slots are between 1 and 31
    #             bus_length = 32
    #             bus_first_port = 1
    #         else:  # addr = 0x0-0x1f
    #             bus_length = 32
    #             bus_first_port = 0
    #         bus = qdevices.QPCIBus(name, bus_type, name, bus_length, bus_first_port)
    #     for addr in params.get("reserved_slots", "").split():
    #         bus.reserve(addr)
    #     return qdevices.QDevice(
    #         driver, pcic_params, aobject=name, parent_bus=parent_bus, child_bus=bus
    #     )


    machine_type = machine.get("type")
    machine_props = machine.get("props")
    # machine_controllers = machine.get("controllers")
    #
    # if self._devices.has_device("pcie-root-port"):
    #     root_port_type = "pcie-root-port"
    # else:
    #     root_port_type = "ioh3420"
    #
    # if self._devices.has_device("pcie-pci-bridge"):
    #     pci_bridge_type = "pcie-pci-bridge"
    # else:
    #     pci_bridge_type = "pci-bridge"

    # FIXME: workaround for invalid_machine is None
    avocado_machine = ""
    machine_params = machine_props.copy()

    # if invalid_machine is not None:
    #     devices = invalid_machine({"type": machine_type})
    # cpu_controller = dict()
    pcie_controller = dict()
    if ":" in machine_type:  # FIXME: To support the arm architecture
        avocado_machine, machine_type = machine_type.split(":", 1)
    machine_params["type"] = machine_type

    if avocado_machine == "invalid_machine":
        devices = create_machine_i440fx({"type": machine_type},
                                        cpu, has_option_device, has_option_global)
    elif machine_type == "pc" or "i440fx" in machine_type:
        devices = create_machine_i440fx(machine_params, cpu,
                                        has_option_device, has_option_global)
    elif "q35" in machine_type:
        devices = create_machine_q35(machine_params, cpu, controller,
                                     has_option_device, has_option_global)
    elif machine_type.startswith("pseries"):
        devices = create_machine_pseries(machine_params, cpu,
                                         has_option_device, has_option_global)
    elif machine_type.startswith("s390"):
        devices = create_machine_s390_virtio(machine_params, cpu)
    # FIXME: support the arm architecture by avocado_machine
    elif avocado_machine == "arm64-pci":
        devices = create_machine_arm64_pci(machine_params, controller)
    elif avocado_machine == "arm64-mmio":
        devices = create_machine_arm64_mmio(machine_params)
    elif avocado_machine == "riscv64-mmio":
        devices = create_machine_riscv64_mmio(machine_params)
    else:
        LOG.warn(
            "Machine type '%s' is not supported "
            "by avocado-vt, errors might occur",
            machine_type,
        )
        devices = create_machine_other(machine_params)

    # FIXME: Skip this part because can not make sure what does it do
    # reserve pci.0 addresses
    # pci_params = params.object_params("pci.0")
    # reserved = pci_params.get("reserved_slots", "").split()
    # if reserved:
    #     for bus in self.__buses:
    #         if bus.aobject == "pci.0":
    #             for addr in reserved:
    #                 bus.reserve(hex(int(addr)))
    #             break

    return devices