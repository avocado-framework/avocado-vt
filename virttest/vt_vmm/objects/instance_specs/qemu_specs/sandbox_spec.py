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


class QemuSpecSandbox(QemuSpec):
    def __init__(self, vm_name, vm_params, node):
        super(QemuSpecSandbox, self).__init__(vm_name, vm_params, node)
        self._parse_params()

    def _define_spec(self):
        sandbox = dict()
        action = self._params.get("qemu_sandbox")
        if not self._has_option("sandbox"):
            return sandbox
        sandbox["action"] = action

        props = {}
        if action == "on":
            props = {
                    "elevateprivileges": self._params.get(
                        "qemu_sandbox_elevateprivileges", "deny"
                    ),
                    "obsolete": self._params.get("qemu_sandbox_obsolete", "deny"),
                    "resourcecontrol": self._params.get(
                        "qemu_sandbox_resourcecontrol", "deny"
                    ),
                    "spawn": self._params.get("qemu_sandbox_spawn", "deny"),
                }
        elif action == "off":
            props = {
                "elevateprivileges": self._params.get("qemu_sandbox_elevateprivileges"),
                "obsolete": self._params.get("qemu_sandbox_obsolete"),
                "resourcecontrol": self._params.get("qemu_sandbox_resourcecontrol"),
                "spawn": self._params.get("qemu_sandbox_spawn"),
            }
        sandbox["props"] = props

        return sandbox

    def _parse_params(self):
        self._spec.update({"sandbox": self._define_spec()})
