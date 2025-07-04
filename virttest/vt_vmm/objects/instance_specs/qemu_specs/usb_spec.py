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
from virttest.vt_vmm.objects.exceptions.instance_exception import InstanceSpecError

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecUSB(QemuSpec):
    def __init__(self, name, vt_params, node, usb):
        super(QemuSpecUSB, self).__init__(name, vt_params, node)
        self._usb = usb
        self._parse_params()

    def _define_spec(self):
        usb_dev = self._usb
        usb_params = self._params.object_params(usb_dev)
        usb = dict()
        usb_props = dict()
        usb["type"] = usb_params.get("usbdev_type")
        usb["bus"] = usb_params.get("pci_bus", "pci.0")

        if usb["type"] == "usb-host":
            usb_props["hostbus"] = usb_params.get("usbdev_option_hostbus")
            usb_props["hostaddr"] = usb_params.get("usbdev_option_hostaddr")
            usb_props["hostport"] = usb_params.get("usbdev_option_hostport")
            vendorid = usb_params.get("usbdev_option_vendorid")
            if vendorid:
                usb_props["vendorid"] = "0x%s" % vendorid
            productid = usb_params.get("usbdev_option_productid")
            if productid:
                usb_props["productid"] = "0x%s" % productid

        if not self._has_device(usb["type"]):
            raise InstanceSpecError(
                "usb device %s not available" % usb["type"])

        if self._has_option("device"):
            usb["id"] = "usb-%s" % usb_dev
            usb_props["bus"] = usb_params.get("usbdev_bus")
            usb_props["port"] = usb_params.get("usbdev_port")
            usb_props["serial"] = usb_params.get("usbdev_serial")
            usb["bus"] = usb_params.get("usb_controller")
        else:
            if "tablet" in usb["type"]:
                usb["type"] = "usb-%s" % usb_dev
            else:
                usb["type"] = "missing-usb-%s" % usb_dev
                LOG.error(
                    "This qemu supports only tablet device; ignoring" " %s",
                    usb_dev
                )

        usb["props"] = usb_props
        return usb

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecUSBDevs(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecUSBDevs, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for usb_name in self._params.objects("usb_devices"):
            self._specs.append(QemuSpecUSB(self._name, self._params,
                                           self._node.tag, usb_name))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"usbs": [usb.spec for usb in self._specs]})
