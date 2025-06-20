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


def create_panic_device(panic, parent_bus, format_cfg):
    params = panic.get("props", {})
    dev = qdevices.QDevice(panic["type"], params=params, parent_bus=parent_bus)
    dev.set_param("id", panic.get("id"), dynamic=True)
    set_cmdline_format_by_cfg(dev, format_cfg, "pvpanic")
    return dev
