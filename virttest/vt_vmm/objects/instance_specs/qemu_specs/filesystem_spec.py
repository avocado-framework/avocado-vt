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


class QemuSpecFilesystem(QemuSpec):
    def __init__(self, name, vt_params, node, fs):
        super(QemuSpecFilesystem, self).__init__(name, vt_params, node)
        self._fs = fs

    def _define_spec(self):
        filesystem = dict()
        fs_driver = dict()
        fs_driver_props = dict()
        fs_source = dict()
        fs_source_props = dict()

        fs = self._fs
        filesystem["id"] = fs
        filesystem_params = self._params.object_params(fs)
        filesystem["target"] = filesystem_params.get("fs_target")
        fs_source["type"] = filesystem_params.get("fs_source_type", "mount")

        if fs_source["type"] == "mount":
            fs_source_props["path"] = filesystem_params.get("fs_source_dir")

        fs_driver["type"] = filesystem_params.get("fs_driver")
        if fs_driver["type"] == "virtio-fs":
            fs_driver_props["binary"] = filesystem_params.get(
                "fs_binary", "/usr/libexec/virtiofsd"
            )
            extra_options = filesystem_params.get("fs_binary_extra_options")
            fs_driver_props["options"] = extra_options
            enable_debug_mode = filesystem_params.get("fs_enable_debug_mode",
                                                      "no")
            fs_driver_props["debug_mode"] = enable_debug_mode

        fs_driver_props.update(
            json.loads(filesystem_params.get("fs_driver_props", "{}"))
        )

        fs_source["props"] = fs_source_props
        filesystem["source"] = fs_source
        fs_driver["props"] = fs_driver_props
        filesystem["driver"] = fs_driver
        return filesystem

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecFilesystems(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecFilesystems, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for fs in self._params.objects("filesystems"):
            self._specs.append(QemuSpecFilesystem(self._name, self._params,
                                                  self._node.tag, fs))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"filesystems": [fs.spec for fs in self._specs]})
