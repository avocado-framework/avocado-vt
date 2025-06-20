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

from dataclasses import dataclass, asdict, field

from avocado_vt.agent.drivers.instance import InstanceInfo
from avocado_vt.agent.drivers.instance import InstanceDriver


@dataclass
class LibvirtInstanceInfo(InstanceInfo):
    pass

class LibvirtInstanceDriver(InstanceDriver):
    def __init__(self):
        super(LibvirtInstanceDriver, self).__init__("libvirt")

    def create_devices(self, spec):
        pass

    def make_cmdline(self):
        pass
