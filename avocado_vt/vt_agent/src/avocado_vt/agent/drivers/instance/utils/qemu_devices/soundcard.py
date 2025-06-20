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


from virttest.qemu_devices import qdevices
from virttest.qemu_devices.utils import set_cmdline_format_by_cfg


def create_soundcard_devices(soundcard, parent_bus, format_cfg):
    devs = []
    soudcard_type = soundcard.get("type")
    if soudcard_type.startswith("SND-"):
        devs.append(qdevices.QStringDevice(soudcard_type, parent_bus=parent_bus))
    else:
        if soudcard_type == "intel-hda":
            dev = qdevices.QDevice(soudcard_type, parent_bus=parent_bus)
            set_cmdline_format_by_cfg(dev, format_cfg, "soundcards")
            devs.append(dev)
            dev = qdevices.QDevice("hda-duplex")
        elif soudcard_type in ["ES1370", "AC97"]:
            dev = qdevices.QDevice(soudcard_type, parent_bus=parent_bus)
        else:
            dev = qdevices.QDevice(soudcard_type, parent_bus=parent_bus)
        set_cmdline_format_by_cfg(dev, format_cfg, "soundcards")
        devs.append(dev)
    return devs
