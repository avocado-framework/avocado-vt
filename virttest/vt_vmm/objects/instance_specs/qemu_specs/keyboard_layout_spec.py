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


class QemuSpecKeyboardLayout(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecKeyboardLayout, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        optsinfo = self._params.get("keyboard_layout")
        options = []
        if optsinfo:
            for info in optsinfo:
                key, val = info[:2]
                if key and val:
                    options.append("%s=%%(%s)s" % (key, key))
                else:
                    options += list(filter(None, info[:2]))
            options = ",".join(options)
            return f"-k {options}"

    def _parse_params(self):
        self._spec.update({"keyboard_layout": self._define_spec()})
