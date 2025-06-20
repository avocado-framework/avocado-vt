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

from managers import vmm

from . import qemu
from . import libvirt


LOG = logging.getLogger("avocado.service." + __name__)

mig_drivers = {
    "qemu": qemu,
    "libvirt": libvirt,
}


VMM = vmm.VirtualMachinesManager()


def get_migration_driver(driver_kind):
    if driver_kind in mig_drivers:
        return mig_drivers[driver_kind]
    else:
        raise ValueError("Unsupported driver kind: %s" % driver_kind)
