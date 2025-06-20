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


def create_watchdog_devices(watchdog, parent_bus):
    devs = []
    watchdog_type = watchdog.get("type")
    if watchdog_type == "itco":
        dev = qdevices.QGlobal("ICH9-LPC", "noreboot", "off")
        devs.append(dev)
    else:
        dev = qdevices.QDevice(watchdog_type, parent_bus=parent_bus)
        devs.append(dev)
    cmd = "-watchdog-action %s" % watchdog.get("action")
    devs.append(qdevices.QStringDevice("watchdog_action", cmdline=cmd))
    return devs
