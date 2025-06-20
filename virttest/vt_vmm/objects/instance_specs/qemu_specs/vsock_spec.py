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


class QemuSpecVsock(QemuSpec):
    def __init__(self, name, vt_params, node, vsock, min_cid):
        super(QemuSpecVsock, self).__init__(name, vt_params, node)
        self._vsock = vsock
        self._min_cid = min_cid
        self._parse_params()

    def _define_spec(self):
        vsock = dict()
        vsock_props = dict()
        vsock["props"] = vsock_props

        _vsock = self._vsock
        min_cid = self._min_cid
        guest_cid = self._node.proxy.network.get_guest_cid(min_cid)
        vsock["id"] = _vsock

        if "-mmio:" in self._params.get("machine_type"):
            vsock["type"] = "vhost-vsock-device"
        elif self._params.get("machine_type").startswith("s390"):
            vsock["type"] = "vhost-vsock-ccw"
        else:
            vsock["type"] = "vhost-vsock-pci"

        vsock["bus"] = self._params.get("pci_bus")
        vsock_props["guest-cid"] = guest_cid
        return vsock

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecVsocks(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecVsocks, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for vsock, min_cid in enumerate(self._params.objects("vsocks"), 3):
            self._specs.append(QemuSpecVsock(self._name, self._params,
                                             self._node.tag, vsock, min_cid))

    def _parse_params(self):
        self._spec.update({"vsocks": [vsock.spec for vsock in self._specs]})
