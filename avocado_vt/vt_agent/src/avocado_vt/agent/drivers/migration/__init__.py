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

from avocado_vt.agent.drivers.migration import libvirt, qemu
from avocado_vt.agent.managers import vmm

LOG = logging.getLogger("avocado.service." + __name__)

mig_driver_backends = {
    "qemu": qemu,
    "libvirt": libvirt,
}


VMM = vmm.VirtualMachinesManager()


def get_migration_driver(backend):
    if backend in mig_driver_backends:
        return mig_driver_backends[backend]
    else:
        raise ValueError("Unsupported driver backend: %s" % backend)
