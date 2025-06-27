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


class QemuSpecLaunchSecurity(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecLaunchSecurity, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        launch_security = dict()

        vm_secure_guest_type = self._params.get("vm_secure_guest_type")
        if vm_secure_guest_type:
            launch_security["id"] = "lsec0"
            security_props = dict()

            if vm_secure_guest_type == "sev":
                launch_security["type"] = "sev-guest"
                security_props["policy"] = int(self._params.get("vm_sev_policy", 3))
                security_props["cbitpos"] = int(self._params["vm_sev_cbitpos"])
                security_props["reduced_phys_bits"] = int(
                    self._params["vm_sev_reduced_phys_bits"]
                )

                if self._params.get("vm_sev_session_file"):
                    security_props["session-file"] = self._params["vm_sev_session_file"]
                if self._params.get("vm_sev_dh_cert_file"):
                    security_props["dh-cert-file"] = self._params["vm_sev_dh_cert_file"]

                if self._params.get("vm_sev_kernel_hashes"):
                    security_props["kernel-hashes"] = self._params.get_boolean(
                        "vm_sev_kernel_hashes"
                    )

            elif vm_secure_guest_type == "tdx":
                launch_security["type"] = "tdx-guest"
            else:
                raise ValueError

            launch_security["props"] = security_props

        return launch_security

    def _parse_params(self):
        self._spec.update({"launch_security": self._define_spec()})
