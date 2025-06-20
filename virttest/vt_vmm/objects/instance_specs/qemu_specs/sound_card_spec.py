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


class QemuSpecSoundCard(QemuSpec):
    def __init__(self, name, vt_params, node, soundcard):
        super(QemuSpecSoundCard, self).__init__(name, vt_params, node)
        self._soundcard = soundcard
        self._parse_params()

    def _define_spec(self):
        bus = self._get_pci_bus(self._params, "soundcard")
        soundcard = {}
        if "hda" in self._soundcard:
            soundcard["type"] = "intel-hba"
        elif self._soundcard in ("es1370", "ac97"):
            soundcard["type"] = self._soundcard.upper()
        else:
            soundcard["type"] = self._soundcard

        soundcard["bus"] = bus
        return soundcard

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecSoundCards(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecSoundCards, self).__init__(name, vt_params, node)
        self._soundcards = []
        self._parse_params()

    def _define_spec(self):
        if self._params.get("soundcards"):
            for sound_device in self._params.get("soundcards").split(","):
                self._soundcards.append(QemuSpecSoundCard(self._name,
                                                          self._params,
                                                          self._node.tag,
                                                          sound_device))

    def _parse_params(self):
        self._define_spec()
        self.update({"soundcards": [soundcard.spec for soundcard in self._soundcards]})
