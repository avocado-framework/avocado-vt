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


class QemuSpecGraphic(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecGraphic, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        graphic = dict()
        graphic_props = dict()
        graphic_type = self._params.get("display")

        if graphic_type == "vnc":
            graphic_props["password"] = self._params.get("vnc_password", "no")
            vnc_extra_params = self._params.get("vnc_extra_params")
            if vnc_extra_params:
                for kay, val in vnc_extra_params.strip(",").split(",").split("=", 1):
                    graphic_props[kay] = val

        graphic["type"] = graphic_type
        graphic["props"] = graphic_props
        return graphic

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecGraphics(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecGraphics, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        self._specs.append(QemuSpecGraphic(self._name, self._params, self._node.tag,))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"graphics": [graphic.spec for graphic in self._specs]})
