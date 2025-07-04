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


import json
import logging

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecTPM(QemuSpec):
    def __init__(self, name, vt_params, node, tpm):
        super(QemuSpecTPM, self).__init__(name, vt_params, node)
        self._tpm = tpm
        self._parse_params()

    def _define_spec(self):
        _tpm = self._tpm
        tpm_params = self._params.object_params(_tpm)
        tpm = dict()
        tpm["id"] = _tpm
        tpm_props = dict()
        tpm_model = dict()
        tpm_model_type = tpm_params.get("tpm_model")
        tpm_model_props = dict()
        tpm["type"] = tpm_params.get("tpm_type")
        tpm_props["version"] = tpm_params.get("tpm_version")

        if (
                tpm["type"] == "emulator"
        ):  # how to define the bin parameter with different nodes?
            tpm_props["bin"] = tpm_params.get("tpm_bin", "/usr/bin/swtpm")
            tpm_props["setup_bin"] = tpm_params.get(
                "tpm_setup_bin", "/usr/bin/swtpm_setup"
            )
            tpm_props["bin_extra_options"] = tpm_params.get(
                "tpm_bin_extra_options")
            tpm_props["setup_bin_extra_options"] = tpm_params.get(
                "tpm_setup_bin_extra_options"
            )

        elif tpm["type"] == "passthrough":
            tpm_props["path"] = self._params.get("tpm_device_path")

        tpm["props"] = tpm_props
        tpm_model_props.update(
            json.loads(tpm_params.get("tpm_model_props", "{}")))
        tpm_model["type"] = tpm_model_type
        tpm_model["props"] = tpm_model_props

        tpm["model"] = tpm_model

        return tpm

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecTPMs(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecTPMs, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for tpm in self._params.objects("tpms"):
            self._specs.append(QemuSpecTPM(self._name, self._params,
                                           self._node.tag, tpm))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"tpms": [tpm.spec for tpm in self._specs]})
