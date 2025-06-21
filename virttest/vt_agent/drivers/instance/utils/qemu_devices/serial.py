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


import os
import logging

from avocado.utils import process

from virttest import data_dir
from virttest import utils_misc
from virttest.qemu_devices import qdevices
from virttest.utils_params import Params

LOG = logging.getLogger("avocado.service." + __name__)


def create_serial_devices(dev_container, serial, count, parent_bus, machine_type,
                          os_arch, has_option_chardev, has_device_serial, driver_id, serial_count):
    def __get_serial_console_filename(name):
        if name:
            return os.path.join(
                data_dir.get_tmp_dir(),
                "serial-%s-%s" % (name, driver_id)
            )
        return os.path.join(data_dir.get_tmp_dir(),
                            "serial-%s" % driver_id)

    devs = []

    serial_type = serial["type"]
    serial_id = serial["id"]
    serial_props = serial["props"]

    backend = serial.get("backend")
    backend_props = backend.get("props")
    serial_filename = backend_props.get("path")
    if serial_filename:
        serial_dirname = os.path.dirname(serial_filename)
        if not os.path.isdir(serial_dirname):
            os.makedirs(serial_dirname)
    else:
        serial_filename = __get_serial_console_filename(serial_id)

    backend_props["path"] = serial_filename

    # Arm lists "isa-serial" as supported but can't use it,
    # fallback to "-serial"
    legacy_cmd = " -serial unix:'%s',server=on,wait=off" % serial_filename
    legacy_dev = qdevices.QStringDevice("SER-%s" % serial_id,
                                        cmdline=legacy_cmd)
    arm_serial = serial_type == "isa-serial" and "arm" in machine_type
    if (
            arm_serial
            or not has_option_chardev
            or not has_device_serial
    ):
        devs.append(legacy_dev)
        return devs

    chardev_id = f"chardev_{serial_id}"

    # FIXME: convert to Params
    params = Params()
    for k, v in backend_props.items():
        if k == "port" and isinstance(v, (list, tuple)):
            host = backend_props.get("host")
            free_ports = utils_misc.find_free_ports(
                v[0], v[1], serial_count, host)
            params[k] = free_ports[count]
        params[k] = v
    params["id"] = chardev_id

    backend = serial["backend"]["type"]
    if backend in [
        "unix_socket",
        "file",
        "pipe",
        "serial",
        "tty",
        "parallel",
        "parport",
    ]:
        if backend == "pipe":
            filename = params.get("path")
            process.system("mkfifo %s" % filename)

    dev = qdevices.CharDevice(params, chardev_id)
    devs.append(dev)

    serial_props["id"] = serial_id
    bus = serial.get("bus")
    bus_type = None
    if serial_type.startswith("virt"):
        if "-mmio" in machine_type:
            controller_suffix = "device"
        elif machine_type.startswith("s390"):
            controller_suffix = "ccw"
        else:
            controller_suffix = "pci"
        bus_type = "virtio-serial-%s" % controller_suffix

    if serial_type.startswith("virt"):
        bus_params = serial_props.copy()
        if bus_params.get("name"):
            del bus_params["name"]
            del bus_params["id"]

        if not bus or bus == "<new>":
            if bus_type == "virtio-serial-device":
                pci_bus = {"type": "virtio-bus"}
            elif bus_type == "virtio-serial-ccw":
                pci_bus = None
            else:
                pci_bus = {"aobject": "pci.0"}
            if bus != "<new>":
                bus = dev_container.get_first_free_bus(
                    {"type": "SERIAL", "atype": bus_type},
                    [None, serial_props.get("nr")]
                )
            #  Multiple virtio console devices can't share a single bus
            if bus is None or bus == "<new>" or serial_type == "virtconsole":
                _hba = bus_type.replace("-", "_") + "%s"
                bus = dev_container.idx_of_next_named_bus(_hba)
                bus = dev_container.list_missing_named_buses(
                    _hba, "SERIAL", bus + 1)[-1]
                LOG.debug("list missing named bus: %s", bus)
                bus_params["id"] = bus
                devs.append(
                    qdevices.QDevice(
                        bus_type,
                        bus_params,
                        bus,
                        pci_bus,
                        qdevices.QSerialBus(bus, bus_type, bus),
                    )
                )
            else:
                bus = bus.busid
        dev = qdevices.QDevice(
            serial_type, serial_props, parent_bus={"busid": bus})

    elif serial_type.startswith("pci"):
        bus = parent_bus
        dev = qdevices.QDevice(serial_type, {"id": serial_id}, parent_bus=bus)

    else:  # none virtio type, generate serial device directly
        dev = qdevices.QDevice(serial_type, {"id": serial_id})
        # Workaround for console issue, details:
        # http://lists.gnu.org/archive/html/qemu-ppc/2013-10/msg00129.html
        if (
                "ppc" in os_arch
                and serial_type == "spapr-vty"
        ):
            reg = 0x30000000 + 0x1000 * count
            dev.set_param("reg", reg)

    dev.set_param("chardev", chardev_id)
    devs.append(dev)

    return devs
