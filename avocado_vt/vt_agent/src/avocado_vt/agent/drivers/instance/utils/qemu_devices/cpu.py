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


def create_cpu_devices(cpu):
    def _get_pci_parent_bus(bus):
        if bus:
            parent_bus = {"aobject": bus}
        else:
            parent_bus = None
        return parent_bus

    def __add_smp():
        smp = cpu_topology.get("smp")
        vcpu_maxcpus = cpu_topology.get("maxcpus")
        vcpu_cores = cpu_topology.get("cores")
        vcpu_threads = cpu_topology.get("threads")
        vcpu_dies = cpu_topology.get("dies")
        vcpu_clusters = cpu_topology.get("clusters")
        vcpu_drawers = cpu_topology.get("drawers")
        vcpu_books = cpu_topology.get("books")
        vcpu_sockets = cpu_topology.get("sockets")

        smp_str = " -smp %d" % smp
        if vcpu_maxcpus:
            smp_str += ",maxcpus=%s" % vcpu_maxcpus
        if vcpu_cores:
            smp_str += ",cores=%s" % vcpu_cores
        if vcpu_threads:
            smp_str += ",threads=%s" % vcpu_threads
        if vcpu_dies:
            smp_str += ",dies=%s" % vcpu_dies
        if vcpu_clusters:
            smp_str += ",clusters=%s" % vcpu_clusters
        if vcpu_drawers:
            smp_str += ",drawers=%s" % vcpu_drawers
        if vcpu_books:
            smp_str += ",books=%s" % vcpu_books
        if vcpu_sockets:
            smp_str += ",sockets=%s" % vcpu_sockets
        return smp_str

    def __add_cpu_flags():
        cmd = " -cpu '%s'" % cpu_info["model"]
        if cpu_info.get("vender"):
            cmd += ',vendor="%s"' % cpu_info.get("vender")
        if cpu_info.get("flags"):
            if not cpu_info.get("flags").startswith(","):
                cmd += ","
            cmd += "%s" % cpu_info.get("flags")
        if cpu_info.get("family"):
            cmd += ",family=%s" % cpu_info.get("family")
        return cmd

    devs = []

    cpu_topology = cpu.get("topology")
    dev = qdevices.QStringDevice("smp", cmdline=__add_smp())
    devs.append(dev)

    cpu_info = cpu.get("info")
    dev = qdevices.QStringDevice("cpu", cmdline=__add_cpu_flags())
    devs.append(dev)

    devices = cpu.get("devices")
    if devices:
        for device in devices:
            dev = qdevices.QCPUDevice(
                devices.get("type"),
                device.get("enable"),
                params=device.get("props"),
                parent_bus=_get_pci_parent_bus(device.get("bus")),
            )
            devs.append(dev)
        else:
            raise ValueError("Unsupported CPU device type")

    return devs
