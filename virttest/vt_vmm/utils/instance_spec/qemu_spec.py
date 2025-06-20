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
import json

from virttest.vt_vmm.objects.instance_specs import qemu_specs as instance_spec_qemu

LOG = logging.getLogger("avocado." + __name__)


def define_instance_specs(vm_name, vm_params, node):
    """
    Define all the related specs of the instance.

    :param vm_name: The VM name
    :type vm_name: str
    :param vm_params: The VM's parameters
    :type vm_params: utils_params.Params
    :param node: The related node of the instance
    :type node: vt_cluster.node.Node
    :return: The related specs
    :rtype: list
    """
    specs = list()

    specs.append(instance_spec_qemu.QemuSpecName(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecUUID(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecPreConfig(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecSandbox(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecDefaults(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecMachine(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecFirmware(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecControllers(vm_name, vm_params, node))
    specs.append(
        instance_spec_qemu.QemuSpecLaunchSecurity(vm_name, vm_params, node))
    specs.append(
        instance_spec_qemu.QemuSpecIOMMU(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecVGA(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecWatchDog(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecMemory(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecCPU(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecNuma(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecSoundCards(vm_name, vm_params, node))
    specs.append(
        instance_spec_qemu.QemuSpecMonitors(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecPanics(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecVMCoreInfo(vm_name, vm_params, node))
    specs.append(
        instance_spec_qemu.QemuSpecSerials(vm_name, vm_params, node))
    specs.append(
        instance_spec_qemu.QemuSpecRngs(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecDebug(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecUSBDevs(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecIOThreads(vm_name, vm_params, node))
    specs.append(
        instance_spec_qemu.QemuSpecThrottleGroups(vm_name, vm_params, node))
    specs.append(
        instance_spec_qemu.QemuSpecDisks(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecEncryption(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecAuth(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecSecret(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecFilesystems(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecNets(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecVsocks(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecOS(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecGraphics(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecRTC(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecTPMs(vm_name, vm_params, node))
    specs.append(
        instance_spec_qemu.QemuSpecPowerManagement(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecInputs(vm_name, vm_params, node))
    specs.append(instance_spec_qemu.QemuSpecBalloons(vm_name, vm_params, node))
    specs.append(
        instance_spec_qemu.QemuSpecKeyboardLayout(vm_name, vm_params, node))

    spec = {}
    for _spec in specs:
        spec.update(_spec.spec)

    spec_str = json.dumps(spec, indent=4, separators=(",", ": "))
    LOG.debug(f"The instance spec: \n{spec_str}")

    return specs


def define_net_device_spec(vm_name, vm_params, node, nic_name):
    """
    Define the net device spec.

    :param vm_name: The VM name
    :type vm_name: str
    :param vm_params: The VM's parameters
    :type vm_params: utils_params.Params
    :param node: The related node tage of the instance
    :type node: str
    :param nic_name: The nic name
    :type nic_name: str
    :return: The disk spec
    :rtype: virttest.vt_vmm.objects.instance_specs.QemuSpecNet
    """
    return instance_spec_qemu.QemuSpecNet(vm_name, vm_params, node, nic_name)


def define_memory_device_spec(vm_name, vm_params, node, mem_name):
    """
    Define the memory device spec.

    :param vm_name: The VM name
    :type vm_name: str
    :param vm_params: The VM's parameters
    :type vm_params: utils_params.Params
    :param node: The related node tage of the instance
    :type node: str
    :param mem_name: The memory name
    :type mem_name: str
    :return: The disk spec
    :rtype: virttest.vt_vmm.objects.instance_specs.QemuSpecMemoryDevice
    """
    return instance_spec_qemu.QemuSpecMemoryDevice(vm_name, vm_params, node, mem_name)


def define_disk_device_spec(vm_name, vm_params, node, disk_name):
    """
    Define the disk device spec.

    :param vm_name: The VM name
    :type vm_name: str
    :param vm_params: The VM's parameters
    :type vm_params: utils_params.Params
    :param node: The related node tage of the instance
    :type node: str
    :param disk_name: The disk name
    :type disk_name: str
    :return: The disk spec
    :rtype: virttest.vt_vmm.objects.instance_specs.QemuSpecDisk
    """
    return instance_spec_qemu.QemuSpecDisk(vm_name, vm_params, node, disk_name)
