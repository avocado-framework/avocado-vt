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


def create_vga_device(vga, parent_bus, format_cfg):
    vga_type = vga.get("type")
    if vga_type and vga_type.startswith("VGA-"):
        vga = vga_type.split("VGA-")[-1]
        cmdline = " -vga %s" % vga
        dev = qdevices.QStringDevice(vga_type, cmdline=cmdline, parent_bus=parent_bus)
    else:
        dev = qdevices.QDevice(vga_type, parent_bus=parent_bus)
    set_cmdline_format_by_cfg(dev, format_cfg, "vga")

    return dev
