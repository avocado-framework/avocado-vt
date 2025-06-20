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
import six

from virttest import utils_misc

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecRng(QemuSpec):
    def __init__(self, name, vt_params, node, rng):
        super(QemuSpecRng, self).__init__(name, vt_params, node)
        self._rng = rng
        self._parse_params()

    def _define_spec(self):
        rng = dict()
        rng_props = dict()
        rng_backend = dict()
        rng_backend_props = dict()

        rng_params = self._params.object_params(self._rng)
        dev_id = utils_misc.generate_random_string(8)
        rng["id"] = f"virtio-rng-{dev_id}"
        rng["bus"] = self._get_pci_bus(rng_params, "vio_rng", True)
        rng["type"] = "pci"
        machine_type = self.params.get("machine_type", "pc")
        if "s390" in machine_type:
            rng["type"] = "ccw"

        for pro, val in six.iteritems(rng_params):
            suffix = "_%s" % "virtio-rng"
            if pro.endswith(suffix):
                idx = len(suffix)
                rng_props[pro[:-idx]] = val

        rng["props"] = rng_props

        if rng_params.get("backend"):
            if rng_params.get("backend") == "rng-builtin":
                backend_type = "builtin"
            elif rng_params.get("backend") == "rng-random":
                backend_type = "random"
            elif rng_params.get("backend") == "rng-egd":
                backend_type = "egd"
            else:
                raise NotImplementedError

            rng_backend["type"] = backend_type

        for pro, val in six.iteritems(rng_params):
            suffix = "_%s" % rng_params["backend_type"]
            if pro.endswith(suffix):
                idx = len(suffix)
                rng_backend_props[pro[:-idx]] = val

        dev_id = utils_misc.generate_random_string(8)
        rng_backend["id"] = "%s-%s" % (rng_params["backend_type"], dev_id)

        rng_backend_chardev = dict()
        if rng_params["backend_type"] == "chardev":
            rng_backend_chardev["type"] = rng_params["rng_chardev_backend"]

            for pro, val in six.iteritems(rng_params):
                suffix = "_%s" % rng_params[
                    "%s_type" % rng_backend_chardev["type"]]
                if pro.endswith(suffix):
                    idx = len(suffix)
                    rng_backend_chardev["props"][pro[:-idx]] = val

            dev_id = utils_misc.generate_random_string(8)
            dev_id = "%s-%s" % (
                rng_params["%s_type" % rng_backend_chardev["type"]],
                dev_id,
            )
            rng_backend_chardev["id"] = dev_id
        if rng_backend_chardev:
            rng_backend["props"]["chardev"] = rng_backend_chardev

        rng_backend["props"] = rng_backend_props
        rng["backend"] = rng_backend
        return rng

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecRngs(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecRngs, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for rng_name in self._params.objects("virtio_rngs"):
            self._specs.append(QemuSpecRng(self._name, self._params,
                                           self._node.tag, rng_name))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"rngs": [rng.spec for rng in self._specs]})
