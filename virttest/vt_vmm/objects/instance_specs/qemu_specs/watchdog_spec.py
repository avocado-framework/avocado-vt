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


class QemuSpecWatchDog(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecWatchDog, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        watchdog = dict()

        if self._params.get("enable_watchdog", "no") == "yes":
            watchdog["type"] = self._params.get("watchdog_device_type")
            if watchdog["type"] and self._has_device(watchdog["type"]):
                if self._is_pci_device(watchdog["type"]):
                    watchdog["bus"] = self._get_pci_bus(self._params, None, False)
            watchdog["action"] = self._params.get("watchdog_action", "reset")

        return watchdog

    def _parse_params(self):
        self._spec.update({"watchdog": self._define_spec()})
