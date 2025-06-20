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

from virttest import data_dir
from virttest.qemu_devices import qdevices


def create_debug_devices(
    dev_container, debug, parent_bus, machine_type, driver_id, uuid, instance_id
):
    devs = []
    debug_type = debug.get("type")

    if debug_type == "isa-debugcon":
        if not dev_container.has_device(debug_type):
            cmd = ""
        else:
            default_id = "seabioslog_id_%s" % driver_id
            filename = os.path.join(data_dir.get_tmp_dir(), "seabios-%s" % driver_id)
            cmd = f" -chardev socket,id={default_id},path={filename},server=on,wait=off"
            cmd += f" -device isa-debugcon,chardev={default_id},iobase=0x402"
        dev = qdevices.QStringDevice("isa-log", cmdline=cmd)
        devs.append(dev)

    elif debug_type == "anaconda_log":
        chardev_id = "anacondalog_chardev_%s" % uuid
        vioser_id = "anacondalog_vioser_%s" % uuid
        filename = os.path.join(data_dir.get_tmp_dir(), "anaconda-%s" % instance_id)
        # self.logs["anaconda"] = filename # FIXEME:
        dev = qdevices.QCustomDevice("chardev", backend="backend")
        dev.set_param("backend", "socket")
        dev.set_param("id", chardev_id)
        dev.set_param("path", filename)
        dev.set_param("server", "on")
        dev.set_param("wait", "off")
        devs.append(dev)

        if "-mmio:" in machine_type:
            dev = qdevices.QDevice("virtio-serial-device")
        elif machine_type.startswith("s390"):
            dev = qdevices.QDevice("virtio-serial-ccw")
        else:
            parent_bus = parent_bus
            dev = qdevices.QDevice("virtio-serial-pci", parent_bus=parent_bus)
        dev.set_param("id", vioser_id)
        devs.append(dev)
        dev = qdevices.QDevice("virtserialport")
        dev.set_param("bus", "%s.0" % vioser_id)
        dev.set_param("chardev", chardev_id)
        dev.set_param("name", "org.fedoraproject.anaconda.log.0")
        devs.append(dev)
    else:
        raise NotImplementedError(debug_type)

    return devs
