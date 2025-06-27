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


class QemuSpecIOThread(QemuSpec):
    def __init__(self, name, vt_params, node, iothread):
        super(QemuSpecIOThread, self).__init__(name, vt_params, node)
        self._iothread = iothread
        self._parse_params()

    def _define_spec(self):
        iothread = dict()
        iothread_props = dict()

        iothread["id"] = self._iothread
        iothread_params = self._params.object_params(iothread)

        for key, val in {"iothread_poll_max_ns": "poll-max-ns"}.items():
            if key in iothread_params:
                iothread_props[val] = iothread_params.get(key)

        iothread["props"] = iothread_props
        return iothread

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecIOThreads(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecIOThreads, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for iothread in self._params.objects("iothreads"):
            self._specs.append(QemuSpecIOThread(self._name, self._params,
                                                self._node.tag, iothread))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"iothreads": [iothread.spec for iothread in self._specs]})
