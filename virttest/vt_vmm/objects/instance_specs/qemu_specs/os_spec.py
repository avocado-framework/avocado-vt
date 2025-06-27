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
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>


import logging

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecOS(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecOS, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        os = dict()

        os["arch"] = self._params.get("vm_arch_name", "auto")
        os["kernel"] = self._params.get("kernel")
        os["initrd"] = self._params.get("initrd")
        os["cmdline"] = self._params.get("kernel_params")

        os["boot"] = dict()
        os["boot"]["menu"] = self._params.get("boot_menu")
        os["boot"]["order"] = self._params.get("boot_order")
        os["boot"]["once"] = self._params.get("boot_once")
        os["boot"]["strict"] = self._params.get("boot_strict")
        os["boot"]["reboot_time"] = self._params.get("boot_reboot_timeout")
        os["boot"]["splash_time"] = self._params.get("boot_splash_time")

        os["bios"] = self._params.get("bios_path")
        return os

    def _parse_params(self):
        self._spec.update({"os": self._define_spec()})
