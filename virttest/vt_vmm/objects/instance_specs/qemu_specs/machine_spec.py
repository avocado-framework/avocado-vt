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


class QemuSpecMachine(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecMachine, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        machine = dict()
        machine_props = dict()
        machine_type = self._params.get('machine_type')
        machine_accel = self._params.get('vm_accelerator')

        if machine_accel:
            machine_props["accel"] = machine_accel

        if self._params.get("disable_hpet") == "yes":
            machine_props["hpet"] = False
        elif self._params.get("disable_hpet") == "no":
            machine_props["hpet"] = True

        machine_type_extra_params = self._params.get("machine_type_extra_params", "")
        for keypair_str in machine_type_extra_params.split(","):
            if not keypair_str:
                continue
            keypair = keypair_str.split("=", 1)
            if len(keypair) < 2:
                keypair.append("NO_EQUAL_STRING")
            machine_props[keypair[0]] = keypair[1]

        avocado_machine = ''
        invalid_machine = None
        if not machine_type:
            for m_name, m_desc in self._qemu_machines_info.items():
                if '(default)' in m_desc:
                    machine_type = m_name
                    break
            else:
                if machine_type is None:
                    machine_type = "<unspecified>"
        else:
            split_machine_type = machine_type.split(':', 1)
            if len(split_machine_type) > 1:
                avocado_machine, machine_type = split_machine_type

            if machine_type in self._qemu_machines_info:
                machine["type"] = machine_type
            elif self._params.get("invalid_machine_type", "no") == "yes":
                # For negative testing pretend the unsupported machine is
                # similar to i440fx one (1 PCI bus, ..)
                # FIXME: support the case "invalid_machine"
                invalid_machine = "invalid_machine"
            else:
                raise InstanceSpecError("Unsupported machine type %s." % (machine_type))

        # FIXME: Support the invalid_machine case
        if invalid_machine is not None:
            machine["type"] = f"{invalid_machine}:{machine_type}"
        # FIXME: Support the avocado_machine cases
        if machine_type in self._qemu_machines_info:
            if avocado_machine in ('arm64-pci', 'arm64-mmio', 'riscv64-mmio', ):
                machine["type"] = f"{avocado_machine}:{machine_type}"
        else:
            LOG.warn("Machine type '%s' is not supported "
                     "by avocado-vt, errors might occur",
                     machine_type)
            machine["type"] = f"unknown:{machine_type}"
        # TODO: Support the vm_pci_hole64_fix case
        # if params.get("vm_pci_hole64_fix"):
        #     if machine_type.startswith('pc'):
        #         devices.append(qdevices.QGlobal("i440FX-pcihost", "x-pci-hole64-fix", "off"))
        #     if machine_type.startswith('q35'):
        #         devices.append(qdevices.QGlobal("q35-pcihost", "x-pci-hole64-fix", "off"))

        # TODO: What's purpose of the following part?
        # reserve pci.0 addresses
        # pci_params = params.object_params('pci.0')
        # reserved = pci_params.get('reserved_slots', '').split()
        # if reserved:
        #     for bus in self.__buses:
        #         if bus.aobject == "pci.0":
        #             for addr in reserved:
        #                 bus.reserve(hex(int(addr)))
        #             break
        machine["props"] = machine_props
        return machine

    def _parse_params(self):
        self._spec.update({"machine": self._define_spec()})
