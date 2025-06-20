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

from virttest import cpu

LOG = logging.getLogger("avocado.service." + __name__)


def get_cpu_info_from_virsh(arch_name, machine_type):
    """
    Get the CPU info for a given arch and machine type.
    :param arch_name:
    :param machine_type:
    :return:
    """
    LOG.info("Getting CPU info for arch %s and machine type %s", arch_name, machine_type)
    params = {"vm_arch_name": arch_name, "machine_type": machine_type}
    return cpu.get_cpu_info_from_virsh(params)


def get_qemu_best_cpu_info(qemu_binary="qemu", default_cpu_model=None):
    """
    Get the best cpu model and features available for qemu.
    """
    LOG.info("Getting the best cpu model and features for qemu")
    cpu_info = {}
    cpu_model = default_cpu_model
    host_cpu_models = cpu.get_host_cpu_models()
    qemu_cpu_models = cpu.get_qemu_cpu_models(qemu_binary)
    # Let's try to find a suitable model on the qemu list
    for host_cpu_model in host_cpu_models:
        if host_cpu_model in qemu_cpu_models:
            cpu_model = host_cpu_model
            break

    # Expand if needed
    cpu_flags = ""
    cpu_info["model"] = cpu_model
    cpu_info["flags"] = cpu_flags
    return cpu_info


def recombine_qemu_cpu_flags(base, suggestion):
    """
    Recombine the cpu flags in base with suggestion
    """
    LOG.info("Recombining qemu cpu flags: base=%s, suggestion=%s", base, suggestion)
    return cpu.recombine_qemu_cpu_flags(base, suggestion)
