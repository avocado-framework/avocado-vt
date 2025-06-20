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
from virttest.utils_params import Params


def create_filesystem_device(filesystem, machine_type, sock_name):
    fs_type = filesystem["type"]
    fs_source = filesystem["source"]
    fs_source_type = fs_source["type"]
    fs_source_props = fs_source["props"]
    fs_target = filesystem["target"]
    fs_driver = filesystem["driver"]
    fs_driver_type = fs_driver["type"]
    fs_driver_props = fs_driver["props"]

    qbus_type = "PCI"
    if machine_type.startswith("q35") or machine_type.startswith("arm64"):
        qbus_type = "PCIE"

    devices = []
    if fs_driver_type == "virtio-fs":
        sock_path = os.path.join(data_dir.get_tmp_dir(), sock_name)
        vfsd = qdevices.QVirtioFSDev(
            filesystem["id"],
            fs_driver_props["binary"],
            sock_path,
            fs_source_props["path"],
            fs_driver_props["options"],
            fs_driver_props["debug_mode"],
        )
        devices.append(vfsd)

        char_params = Params()
        char_params["backend"] = "socket"
        char_params["id"] = "char_%s" % vfsd.get_qid()
        sock_bus = {"busid": sock_path}
        char = qdevices.CharDevice(char_params, parent_bus=sock_bus)
        char.set_aid(vfsd.get_aid())
        devices.append(char)

        qdriver = "vhost-user-fs"
        if "-mmio:" in machine_type:
            qdriver += "-device"
            qbus_type = "virtio-bus"
        elif machine_type.startswith("s390"):
            qdriver += "-ccw"
            qbus_type = "virtio-bus"
        else:
            qdriver += "-pci"

        bus = filesystem["bus"]
        if bus is None:
            bus = {"type": qbus_type}

        dev_params = {
            "id": "vufs_%s" % vfsd.get_qid(),
            "chardev": char.get_qid(),
            "tag": fs_target,
        }
        dev_params.update(fs_driver_props)
        vufs = qdevices.QDevice(qdriver, params=fs_driver_props, parent_bus=bus)
        vufs.set_aid(vfsd.get_aid())
        devices.append(vufs)
    else:
        raise ValueError("unsupported filesystem driver type")
    return devices
