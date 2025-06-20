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

from ..qemu_specs.spec import QemuSpec

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecBalloon(QemuSpec):
    def __init__(self, name, vt_params, node, balloon):
        super(QemuSpecBalloon, self).__init__(name, vt_params, node)
        self._balloon = balloon
        self._parse_params()

    def _define_spec(self):
        balloon_device = self._balloon
        balloon_params = self._params.object_params(balloon_device)
        balloon = dict()
        balloon["id"] = balloon_device
        balloon["type"] = balloon_params["balloon_dev_devid"]
        balloon_props = dict()

        balloon_props["old_format"] = (
                balloon_params.get("balloon_use_old_format", "no") == "yes"
        )
        balloon_props["deflate_on_oom"] = balloon_params.get(
            "balloon_opt_deflate_on_oom"
        )
        balloon_props["guest_stats_polling_interval"] = balloon_params.get(
            "balloon_opt_guest_polling"
        )
        balloon_props["free_page_reporting"] = balloon_params.get(
            "balloon_opt_free_page_reporting"
        )

        if balloon_params.get("balloon_dev_add_bus") == "yes":
            balloon["bus"] = self._get_pci_bus(balloon_params, "balloon", True)

        balloon["props"] = balloon_props
        return balloon

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecBalloons(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecBalloons, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for balloon in self._params.objects("balloons"):
            self._specs.append(QemuSpecBalloon(self._name, self._params,
                                               self._node.tag, balloon))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"balloons": [balloon.spec for balloon in self._specs]})
