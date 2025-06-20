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


from virttest.qemu_devices import qdevices
from virttest.qemu_devices.utils import set_cmdline_format_by_cfg


def create_memory(memory, format_cfg):
    devs = []

    memory_machine = memory["machine"]
    memory_machine_backend = memory_machine.get("backend")
    if memory_machine_backend:
        memory_backend_type = memory_machine_backend.get("type")
        memory_machine_props = memory_machine_backend.get("props")
        memory_machine_props.update({"backend": memory_machine_backend})
        dev = qdevices.Memory(memory_backend_type, memory_machine_props)
        dev.set_param("id", memory_machine_backend.get("id"))
        set_cmdline_format_by_cfg(dev, format_cfg, "mem_devs")
        devs.append(dev)

    options = list()
    options.append(memory_machine["size"])
    if memory_machine.get("max_mem"):
        options.append("maxmem=%s" % memory_machine["max_mem"])
        if memory_machine.get("slots"):
            options.append("slots=%s" % memory_machine["slots"])

    cmdline = "-m %s" % ",".join(map(str, options))
    dev = qdevices.QStringDevice("mem", cmdline=cmdline)
    devs.append(dev)

    return devs


def create_memory_devices(memory, format_cfg):
    def _get_pci_parent_bus(bus):
        if bus:
            parent_bus = {"aobject": bus}
        else:
            parent_bus = None
        return parent_bus

    devs = []
    devices = memory.get("devices")
    if devices:
        for device in devices:
            _devs = []
            backend = device["backend"]
            params = backend["props"].copy()
            params.update({"backend": backend["type"]})  # FIXME:
            dev = qdevices.Memory(backend["type"], params)
            dev.set_param("id", backend["id"])
            _devs.append(dev)

            dev_type = device.get("type")
            if dev_type:
                if dev_type in ("nvdimm", "pc-dimm"):
                    dev = qdevices.Dimm(params=device["props"], dimm_type=dev_type)
                    dev.set_param("id", device["id"])
                    if "node" in device.get("props", {}):
                        dev.set_param(
                            "node", int(device["props"]["node"])
                        )  # FIXME: should be handle by qdevice_format
                elif dev_type in (
                    "virtio-mem-pci",
                    "virtio-mem-device",
                ):
                    dev = qdevices.QDevice(
                        driver=dev_type,
                        parent_bus=_get_pci_parent_bus(device["bus"]),
                        params=device["props"],
                    )
                    dev.set_param("id", device["id"])
                _devs.append(dev)

            for dev in _devs:
                set_cmdline_format_by_cfg(dev, format_cfg, "mem_devs")

            # self._spec_devs.append({"spec": device, "devices": _devs})
            devs.extend(_devs)
    return devs
