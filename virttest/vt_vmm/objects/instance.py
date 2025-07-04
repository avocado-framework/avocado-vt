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


import json
import copy

from .exceptions import instance_exception
from .instance_spec import Spec
from .instance_specs.qemu_specs import (QemuSpec, QemuSpecMemoryDevice,
                                        QemuSpecMemory,
                                 QemuSpecDisk, QemuSpecDisks,
                                 QemuSpecPCIeExtraController, QemuSpecPCIController,
                                 QemuSpecUSBController, QemuSpecControllers)
from virttest.vt_vmm.objects.states.instance_state import States


class Instance(object):
    def __init__(self, uuid, name, kind, specs):
        self._uuid = uuid
        self._name = name
        self._kind = kind  # virt driver type. e.g: libvirt, qemu
        self._specs = specs
        self._state = None
        self.node = None  # binding node

    @property
    def uuid(self):
        return self._uuid

    @property
    def name(self):
        return self._name

    @property
    def kind(self):
        return self._kind

    @property
    def specs(self):
        return self._specs

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, state):
        if isinstance(state, States):
            self._state = state
        else:
            raise ValueError

    def format_specs(self, format_type=None):
        raise NotImplementedError

    def update_spec(self, updated_spec):
        if isinstance(updated_spec, Spec):
            self._specs.update(updated_spec)
        else:
            raise instance_exception.InstanceError("No support this type of spec.")

    def insert_spec(self, spec):
        raise NotImplementedError

    def remove_spec(self, spec):
        raise NotImplementedError

    def get_spec(self, spec):
        return NotImplementedError


class InstanceQemu(Instance):
    def __init__(self, uuid, name, specs):
        super(InstanceQemu, self).__init__(uuid, name, "qemu", specs)

    def format_specs(self, format_type=None):
        specs = dict()
        for _spec in self.specs:
            specs.update(_spec.spec)

        if format_type == "xml":
            # TODO: generate xml format spec
            pass
        elif format_type == "json":
            return json.dumps(specs)
        else:
            return specs

    def _get_spec(self, spec_type):
        for _spec in self.specs:
            if isinstance(_spec, spec_type):
                return _spec
        return None

    def insert_spec(self, spec):
        if isinstance(spec, (QemuSpecPCIeExtraController,
                             QemuSpecPCIController,
                             QemuSpecUSBController)):
            ctrl_spec = self._get_spec(QemuSpecControllers)
            ctrl_spec.insert_spec(spec)
        elif isinstance(spec, QemuSpecDisk):
            disks_spec = self._get_spec(QemuSpecDisks)
            disks_spec.insert_spec(spec)
        elif isinstance(spec, QemuSpecMemoryDevice):
            mem_spec = self._get_spec(QemuSpecMemory)
            mem_spec.insert_spec(spec)
        elif isinstance(spec, QemuSpec):
            self.specs.append(spec)
        else:
            raise instance_exception.InstanceError(f"No support this type of spec: {spec}.")

    def remove_spec(self, spec):
        if isinstance(spec, QemuSpecDisk):
            disks_spec = self._get_spec(QemuSpecDisks)
            disks_spec.remove_spec(spec)
        elif isinstance(spec, QemuSpecMemoryDevice):
            mem_spec = self._get_spec(QemuSpecMemory)
            mem_spec.remove_spec(spec)
        elif isinstance(spec, QemuSpec):
            self.specs.remove(spec)
        else:
            raise instance_exception.InstanceError("No such spec in instance.")

    def update_spec(self, update_spec):
        pass

    def query_spec_info(self, condition):
        """
        Query the spec info.

        :param condition: The query condition, format: x.y.z
        :type condition: str
        :return: The spec info
        """
        d = copy.deepcopy(self.format_specs())
        keys = condition.split(".")
        for key in keys:
            d = d.get(key, {})
        return d if d else None


class InstanceLibvirt(Instance):
    def __init__(self, uuid, name, specs):
        super(InstanceLibvirt, self).__init__(uuid, name, "libvirt", specs)
