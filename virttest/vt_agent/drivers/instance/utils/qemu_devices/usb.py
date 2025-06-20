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


def create_usb_device(dev_container, usb, format_cfg):
    usb_type = usb.get("type")
    usb_id = usb.get("id")
    usb_bus = usb.get("bus")
    usb_props = usb.get("props")
    usb_name = usb_id.split("usb-")[-1]

    if dev_container.has_option("device"):
        dev = qdevices.QDevice(usb_type, params=usb_props, aobject=usb_name)
        dev.parent_bus += ({"type": usb_bus},)
    else:
        if "tablet" in usb_type:
            dev = qdevices.QStringDevice(
                usb_type, cmdline="-usbdevice %s" % usb_name
            )
        else:
            dev = qdevices.QStringDevice(usb_type)
    set_cmdline_format_by_cfg(dev, format_cfg, "usbs")
    return dev
