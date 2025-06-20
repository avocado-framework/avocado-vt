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

LOG = logging.getLogger("avocado.service." + __name__)


def create_input_device(dev_container, input, machine_type):
    input_type = input.get("type")
    input_bus = input.get("bus")
    dev = None

    drv_map = {
        "mouse": "virtio-mouse",
        "keyboard": "virtio-keyboard",
        "tablet": "virtio-tablet",
    }
    driver = drv_map.get(input_type)

    if "-mmio:" in machine_type:
        driver += "-device"
    elif machine_type.startswith("s390"):
        driver += "-ccw"
    else:
        driver += "-pci"

    if dev_container.has_device(driver):
        dev = qdevices.QDevice(driver, parent_bus={"type": input_bus})
        dev.set_param("id", "input_%s" % input["id"])
    else:
        LOG.warn("'%s' is not supported by your qemu", driver)

    return dev
