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
# Copyright: Red Hat Inc. 2025 and Avocado contributors
# Authors: Yongxue Hong <yhong@redhat.com>


import logging

from six.moves import xrange
from virttest import arch
from virttest.qemu_devices import qdevices
from virttest.qemu_devices.utils import set_cmdline_format_by_cfg

LOG = logging.getLogger("avocado.service." + __name__)


def create_usb_controller_devices(controller, pci_bus, format_cfg):
    usb_id = controller.get("id")
    usb_type = controller.get("type")
    max_ports = controller.get("max_ports", 6)
    usb = qdevices.QDevice(
        usb_type,
        {},
        usb_id,
        pci_bus,
        qdevices.QUSBBus(max_ports, "%s.0" % usb_id, usb_type, usb_id),
    )

    devs = [usb]
    usb.set_param("id", usb_id)
    usb.set_param("masterbus", controller.get("masterbus"))
    usb.set_param("multifunction", controller.get("multifunction"))
    usb.set_param("firstport", controller.get("firstport"))
    usb.set_param("freq", controller.get("freq"))
    usb.set_param("addr", controller.get("addr"))
    if usb_type == "ich9-usb-ehci1":
        usb.set_param("addr", "1d.7")
        usb.set_param("multifunction", "on")
        if arch.ARCH in ("ppc64", "ppc64le"):
            for i in xrange(2):
                devs.append(qdevices.QDevice("pci-ohci", {}, usb_id))
                devs[-1].parent_bus = pci_bus
                devs[-1].set_param("id", "%s.%d" % (usb_id, i))
                devs[-1].set_param("multifunction", "on")
                devs[-1].set_param("masterbus", "%s.0" % usb_id)
                # current qdevices doesn't support x.y addr. Plug only
                # the 0th one into this representation.
                devs[-1].set_param("addr", "1d.%d" % (3 * i))
                devs[-1].set_param("firstport", 3 * i)
        else:
            for i in xrange(3):
                devs.append(qdevices.QDevice("ich9-usb-uhci%d" % (i + 1), {}, usb_id))
                devs[-1].parent_bus = pci_bus
                devs[-1].set_param("id", "%s.%d" % (usb_id, i))
                devs[-1].set_param("multifunction", "on")
                devs[-1].set_param("masterbus", "%s.0" % usb_id)
                # current qdevices doesn't support x.y addr. Plug only
                # the 0th one into this representation.
                devs[-1].set_param("addr", "1d.%d" % (2 * i))
                devs[-1].set_param("firstport", 2 * i)
    for dev in devs:
        set_cmdline_format_by_cfg(dev, format_cfg, "usbs")

    return devs
