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


from virttest.vt_vmm.objects.migrate_caps.qemu_capabilities import (
    QEMU_MIGRATION_CAPABILITIES,
)
from virttest.vt_vmm.objects.migrate_params.qemu_parameters import QEMU_MIGRATION_PARAMETERS


def get_qemu_migration_capability(virt_capability):
    if virt_capability in QEMU_MIGRATION_CAPABILITIES:
        return QEMU_MIGRATION_CAPABILITIES[virt_capability]
    else:
        raise ValueError(f"Unsupported type for virt capability {virt_capability}")


def get_virt_migration_capability(qemu_capability):
    for virt_capability, qemu_capabilities in QEMU_MIGRATION_CAPABILITIES.items():
        if qemu_capability in qemu_capabilities:
            return virt_capability
    else:
        raise ValueError(
            f"Unsupported type for qemu migration capability {qemu_capability}"
        )


def get_qemu_migration_parameter(virt_parameter):
    if virt_parameter in QEMU_MIGRATION_PARAMETERS:
        return QEMU_MIGRATION_PARAMETERS[virt_parameter]
    else:
        raise ValueError(f"Unsupported type for virt parameter {virt_parameter}")


def get_virt_migration_parameter(qemu_parameter):
    for virt_paramter, qemu_parameters in QEMU_MIGRATION_PARAMETERS.items():
        if qemu_parameter in qemu_parameters:
            return virt_paramter
    else:
        raise ValueError(
            f"Unsupported type for qemu migration parameter {qemu_parameter}"
        )
