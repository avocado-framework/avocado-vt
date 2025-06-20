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


from virttest import utils_misc
from virttest.qemu_devices import qdevices


def create_graphics_device(dev_container, graphic):
    def add_sdl(devices):
        if devices.has_option("sdl"):
            return " -sdl"
        else:
            return ""

    def add_nographic():
        return " -nographic"

    graphic_type = graphic.get("type")
    graphic_props = graphic.get("props")
    cmd = ""
    if graphic_type == "vnc":
        free_port = utils_misc.find_free_port(5900, 6900, sequent=True)
        vnc_port = graphic_props.get("port")
        if vnc_port:
            del graphic_props["port"]
        else:
            vnc_port = free_port
        cmd = " -vnc :%d" % (vnc_port - 5900)
        password = graphic_props.get("password")
        if password:
            del graphic_props["password"]
            if password == "yes":
                cmd += ",password"
        for k, v in graphic_props.items():
            cmd += ",%s" % f"{k}={v}"
    elif graphic_type == "sdl":
        if dev_container.has_option("sdl"):
            cmd = " -sdl"
    elif graphic_type == "nographic":
        cmd = ""
    else:
        raise ValueError(f"unsupported graphic type {graphic_type}")

    return qdevices.QStringDevice("display", cmdline=cmd)
