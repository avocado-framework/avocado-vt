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

from virttest import data_dir, utils_misc
from virttest.qemu_devices import qdevices

LOG = logging.getLogger("avocado.service." + __name__)


def create_os_device(dev_container, os, machine_type):
    def __add_boot(opts):
        if machine_type.startswith("arm") or machine_type.startswith("riscv"):
            LOG.warn(
                "-boot on %s is usually not supported, use " "bootindex instead.",
                machine_type,
            )
            return ""
        if machine_type.startswith("s390"):
            LOG.warn("-boot on s390x only support boot strict=on")
            return "-boot strict=on"
        cmd = " -boot"
        options = []
        for p in list(opts.keys()):
            pattern = "boot .*?(\[,?%s=(.*?)\]|\s+)" % p
            if dev_container.has_option(pattern):
                option = opts[p]
                if option is not None:
                    options.append("%s=%s" % (p, option))
        if dev_container.has_option("boot \[a\|c\|d\|n\]"):
            cmd += " %s" % opts["once"]
        elif options:
            cmd += " %s" % ",".join(options)
        else:
            cmd = ""
        return cmd

    devs = []
    kernel = os.get("kernel")
    if kernel:
        kernel = utils_misc.get_path(data_dir.get_data_dir(), kernel)
        devs.append(qdevices.QStringDevice("kernel", cmdline=" -kernel '%s'" % kernel))

    kernel_params = os.get("cmdline")
    if kernel_params:
        devs.append(
            qdevices.QStringDevice(
                "kernel-params", cmdline=" -append '%s'" % kernel_params
            )
        )

    initrd = os.get("initrd")
    if initrd:
        initrd = utils_misc.get_path(data_dir.get_data_dir(), initrd)
        devs.append(qdevices.QStringDevice("initrd", cmdline=" -initrd '%s'" % initrd))

    boot = os.get("boot")
    if boot:
        if dev_container.has_option("boot"):
            cmd = __add_boot(boot)
            devs.append(qdevices.QStringDevice("bootmenu", cmdline=cmd))

    bios = os.get("bios")
    if bios:
        devs.append(qdevices.QStringDevice("bios", cmdline="-bios %s" % bios))

    return devs
