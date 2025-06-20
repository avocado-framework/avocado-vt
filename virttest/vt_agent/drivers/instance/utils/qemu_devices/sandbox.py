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


def create_sandbox_device(sandbox):
    sandbox_option = ""
    action = sandbox.get("action")
    if action == "on":
        sandbox_option = " -sandbox on"
    elif action == "off":
        sandbox_option = " -sandbox off"

    props = sandbox.get("props")
    if props:
        for opt, val in props.items():
            if val is not None:
                sandbox_option += f",{opt}={val}"

    return qdevices.QStringDevice("qemu_sandbox", cmdline=sandbox_option)
