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


class QemuSpecThrottleGroup(QemuSpec):
    def __init__(self, name, vt_params, node, throttle_group):
        super(QemuSpecThrottleGroup, self).__init__(name, vt_params, node)
        self._throttle_group = throttle_group
        self._parse_params()

    def _define_spec(self):
        iothread = dict()
        iothread_props = dict()
        group_params = self._params.object_params(self._throttle_group)
        iothread["id"] = self._throttle_group
        throttle_group_parameters = group_params.get(
            "throttle_group_parameters", "{}"
        )
        iothread_props.update(json.loads(throttle_group_parameters))
        iothread["props"] = iothread_props
        return iothread

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecThrottleGroups(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecThrottleGroups, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for throttle_group in self._params.objects("throttle_groups"):
            self._specs.append(QemuSpecThrottleGroup(self._name, self._params,
                                                     self._node.tag, throttle_group))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"throttle_groups": [thg.spec for thg in self._specs]})
