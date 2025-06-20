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


class QemuSpecRTC(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecRTC, self).__init__(name, vt_params, node)

    def _define_spec(self):
        rtc = dict()
        rtc["base"] = self._params.get("rtc_base")
        rtc["clock"] = self._params.get("rtc_clock")
        rtc["driftfix"] = self._params.get("rtc_drift")
        return rtc

    def _parse_params(self):
        self._spec.update({"rtc": self._define_spec()})
