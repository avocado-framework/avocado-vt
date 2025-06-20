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


def create_disk_devices(dev_container, disk, parent_bus, format_cfg):
    def define_hbas(
            qtype,
            atype,
            bus,
            unit,
            port,
            qbus,
            pci_bus,
            iothread,
            addr_spec=None,
            num_queues=None,
            bus_props={},
    ):
        """
        Helper for creating HBAs of certain type.
        """
        devices = []
        # AHCI uses multiple ports, id is different
        if qbus == qdevices.QAHCIBus:
            _hba = "ahci%s"
        else:
            _hba = atype.replace("-", "_") + "%s.0"  # HBA id
        _bus = bus
        if bus is None:
            bus = dev_container.get_first_free_bus(
                {"type": qtype, "atype": atype}, [unit, port]
            )
            if bus is None:
                bus = dev_container.idx_of_next_named_bus(_hba)
            else:
                bus = bus.busid
        if isinstance(bus, int):
            for bus_name in dev_container.list_missing_named_buses(_hba, qtype,
                                                                   bus + 1):
                _bus_name = bus_name.rsplit(".")[0]
                bus_params = {"id": _bus_name, "driver": atype}
                if num_queues is not None and int(num_queues) > 1:
                    bus_params["num_queues"] = num_queues
                bus_params.update(bus_props)
                if addr_spec:
                    dev = qdevices.QDevice(
                        params=bus_params,
                        parent_bus=pci_bus,
                        child_bus=qbus(
                            busid=bus_name,
                            bus_type=qtype,
                            addr_spec=addr_spec,
                            atype=atype,
                        ),
                    )
                else:
                    dev = qdevices.QDevice(
                        params=bus_params,
                        parent_bus=pci_bus,
                        child_bus=qbus(busid=bus_name),
                    )
                if iothread:
                    try:
                        _iothread = dev_container.allocate_iothread(iothread,
                                                                    dev)
                    except TypeError:
                        pass
                    else:
                        if _iothread and _iothread not in dev_container:
                            devices.append(_iothread)
                devices.append(dev)
            bus = _hba % bus
        if qbus == qdevices.QAHCIBus and unit is not None:
            bus += ".%d" % unit
        # If bus was not set, don't set it, unless the device is
        # a spapr-vscsi device.
        elif _bus is None and "spapr_vscsi" not in _hba:
            bus = None
        return devices, bus, {"type": qtype, "atype": atype}

    devices = []

    name = disk.get("id")
    source = disk.get("source")
    device = disk.get("device")
    device_props = device.get("props")
    device_bus = device.get("bus")
    iothread = None  # FIXME: skip this at the moment

    # Create the HBA devices
    if device_bus:
        bus_type = device_bus.get("type")
        pci_bus = parent_bus
        device_bus_props = device_bus.get("props").copy()
        bus = device_props.get("bus")
        unit = device_props.get("unit")
        port = device_props.get("port")
        num_queues = device_bus_props.get("num_queues")
        if "num_queues" in device_bus_props:
            del device_bus_props["num_queues"]

        if device["type"] == "ide":
            bus = unit
            dev_parent = {"type": "IDE", "atype": bus_type}
        elif device["type"] == "ahci":
            devs, bus, dev_parent = define_hbas(
                "IDE", "ahci", bus, unit, port, qdevices.QAHCIBus, pci_bus,
                iothread
            )
            devices.extend(devs)
        elif device["type"].startswith("scsi-"):
            qbus = qdevices.QSCSIBus
            addr_spec = device_bus_props.get("addr_spec")
            if "addr_spec" in device_bus_props:
                del device_bus_props["addr_spec"]
            devs, bus, dev_parent = define_hbas("SCSI", bus_type, bus, unit,
                                                port,
                                                qbus, pci_bus, iothread,
                                                addr_spec,
                                                num_queues, device_bus_props)
            devices.extend(devs)

    # create the driver or block node device
    if source:
        protocol_node = source
        protocol_node_type = protocol_node.get("type")
        protocol_node_props = protocol_node.get("props")
        if protocol_node_type == qdevices.QBlockdevProtocolFile.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolFile
        elif protocol_node_type == qdevices.QBlockdevProtocolNullCo.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolNullCo
        elif protocol_node_type == qdevices.QBlockdevProtocolISCSI.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolISCSI
        elif protocol_node_type == qdevices.QBlockdevProtocolRBD.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolRBD
        elif protocol_node_type == qdevices.QBlockdevProtocolGluster.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolGluster
        elif protocol_node_type == qdevices.QBlockdevProtocolNBD.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolNBD
        elif protocol_node_type == qdevices.QBlockdevProtocolNVMe.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolNVMe
        elif protocol_node_type == qdevices.QBlockdevProtocolSSH.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolSSH
        elif protocol_node_type == qdevices.QBlockdevProtocolHTTPS.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolHTTPS
        elif protocol_node_type == qdevices.QBlockdevProtocolHTTP.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolHTTP
        elif protocol_node_type == qdevices.QBlockdevProtocolFTPS.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolFTPS
        elif protocol_node_type == qdevices.QBlockdevProtocolFTP.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolFTP
        elif protocol_node_type == qdevices.QBlockdevProtocolVirtioBlkVhostVdpa.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolVirtioBlkVhostVdpa
        elif protocol_node_type == qdevices.QBlockdevProtocolHostDevice.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolHostDevice
        elif protocol_node_type == qdevices.QBlockdevProtocolBlkdebug.TYPE:
            protocol_cls = qdevices.QBlockdevProtocolBlkdebug
        else:
            raise ValueError(
                "Unsupported protocol node type: %s" % protocol_node_type)
        protocol_node = protocol_cls(name)
        devices.append(protocol_node)
        top_node = protocol_node

        format_node = source.get("format")
        if format_node:
            format_node_type = format_node.get("type")
            format_node_props = format_node.get("props")
            if format_node_type == qdevices.QBlockdevFormatQcow2.TYPE:
                format_cls = qdevices.QBlockdevFormatQcow2
            elif format_node_type == qdevices.QBlockdevFormatRaw.TYPE:
                format_cls = qdevices.QBlockdevFormatRaw
            elif format_node_type == qdevices.QBlockdevFormatLuks.TYPE:
                format_cls = qdevices.QBlockdevFormatLuks
            else:
                raise ValueError(
                    "Unsupported format node type: %s" % format_node_type)
            format_node = format_cls(source.get("id"))
            format_node.add_child_node(protocol_node)
            devices.append(format_node)
            top_node = format_node

        for key, value in protocol_node_props.items():
            if key not in protocol_node.params:
                protocol_node.set_param(key, value)

        if format_node_props:
            for key, value in format_node_props.items():
                if key not in format_node.params:
                    format_node.set_param(key, value)

        if top_node is not protocol_node:
            top_node.set_param("file", protocol_node.get_qid())

    # create the devices
    if device:
        device_type = device.get("type")
        name = device.get("id")
        params = device.get("props")
        params["bus"] = bus

        dev = qdevices.QDevice(device_type, params, name)
        dev.parent_bus += ({"busid": "drive_%s" % name}, dev_parent)
        dev.set_param("id", name)
        devices.append(dev)

    for device in devices:
        set_cmdline_format_by_cfg(device, format_cfg, "images")
    # self._spec_devs.append({"spec": disk, "devices": devices})
    return devices
