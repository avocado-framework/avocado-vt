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


from virttest.qemu_devices.utils import set_cmdline_format_by_cfg

from virttest.qemu_devices import qdevices
from virttest.utils_params import Params

def create_monitor_devices(monitor, has_option_chardev, format_cfg):
    devs = []

    monitor_id = monitor.get("id")
    monitor_type = monitor.get("type")
    monitor_props = monitor.get("props")
    monitor_backend = monitor.get("backend")

    if not has_option_chardev:
        filename = monitor_props.get("filename")
        if monitor_type == "qmp":
            cmd = " -qmp unix:'%s',server,nowait" % filename
        else:
            # The monitor type is "hmp"
            cmd = " -monitor unix:'%s',server,nowait" % filename
        dev = qdevices.QStringDevice("QMP-%s" % monitor_id, cmdline=cmd)
        set_cmdline_format_by_cfg(dev, format_cfg, "monitors")
        devs.append(dev)

    else:
        chardev_id = monitor_backend.get("id")
        # convert the monitor_backend_props to Params mandatory.
        chardev_param = Params(monitor_backend.get("props"))
        chardev_param["id"] = chardev_id
        char_device = qdevices.CharDevice(chardev_param, chardev_id)
        set_cmdline_format_by_cfg(char_device, format_cfg, "monitors")
        devs.append(char_device)

        cmd = " -mon chardev=%s,mode=%s" % (chardev_id, monitor_props["mode"])
        dev = qdevices.QStringDevice("QMP-%s" % monitor_id, cmdline=cmd)
        set_cmdline_format_by_cfg(dev, format_cfg, "monitors")
        devs.append(dev)

    return devs
