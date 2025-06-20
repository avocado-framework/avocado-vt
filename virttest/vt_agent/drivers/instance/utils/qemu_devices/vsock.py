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


def create_vsock_device(vsock, format_cfg):
    vsock_params = vsock.get("props", {})
    vsock_params["id"] = vsock.get("id")
    if vsock.get("bus"):
        parent_bus = {"aobject": vsock["bus"]}
    else:
        parent_bus = None
    dev = qdevices.QDevice(vsock.get("type"), vsock_params, parent_bus=parent_bus)
    set_cmdline_format_by_cfg(dev, format_cfg, "vsocks")
    return dev
