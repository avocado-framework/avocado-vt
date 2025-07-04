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


def create_balloon_device(balloon, machine_type):
    devid = balloon.get("id")
    bus = balloon["bus"]
    if "s390" in machine_type:  # For s390x platform
        model = "virtio-balloon-ccw"
        bus = {"type": bus}
    else:
        model = "virtio-balloon-pci"
    dev = qdevices.QDevice(model, params=balloon.get("props"), parent_bus=bus)
    if devid:
        dev.set_param("id", devid)
    return dev
