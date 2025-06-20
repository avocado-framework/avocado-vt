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
import uuid

from virttest import utils_misc
from virttest.qemu_capabilities import Flags
from virttest.qemu_devices import qdevices
from virttest.utils_params import Params

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec
from virttest.vt_vmm.objects.exceptions.instance_exception import InstanceSpecError


LOG = logging.getLogger("avocado." + __name__)


class QemuSpecMemoryMachine(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecMemoryMachine, self).__init__(name, vt_params, node)
        # self._mem_machine = dict()
        # self._mem_machine["size"] = 0
        # self._mem_machine["slots"] = 0
        # self._mem_machine["max_mem"] = 0
        # self._mem_machine["mem_path"] = ""
        #
        # self._mem_machine_backend = dict()
        # self._mem_machine_backend["id"] = ""
        # self._mem_machine_backend["type"] = ""
        # self._mem_machine_backend["props"] = dict()
        #
        # self._mem_machine["backend"] = self._mem_machine_backend
        #
        # self._mem_machine_spec = {
        #     "machine": self._mem_machine
        # }
        self._parse_params()

    def _define_spec(self):
        machine = dict()
        normalize_data_size = utils_misc.normalize_data_size
        mem = self._params.get("mem", None)
        mem_params = self._params.object_params("mem")
        if mem:
            # if params["mem"] is provided, use the value provided
            mem_size_m = "%sM" % mem_params["mem"]
            mem_size_m = float(normalize_data_size(mem_size_m))
        # if not provided, use automem
        else:
            usable_mem_m = self._node.proxy.memory.get_usable_memory_size(align=512)
            if not usable_mem_m:
                raise InstanceSpecError("Insufficient memory to" " start a VM.")
            LOG.info("Auto set guest memory size to %s MB" % usable_mem_m)
            mem_size_m = usable_mem_m
            machine["size"] = str(int(mem_size_m))

        # vm_mem_limit(max) and vm_mem_minimum(min) take control here
        if mem_params.get("vm_mem_limit"):
            max_mem_size_m = self._params.get("vm_mem_limit")
            max_mem_size_m = float(normalize_data_size(max_mem_size_m))
            if mem_size_m >= max_mem_size_m:
                LOG.info("Guest max memory is limited to %s" % max_mem_size_m)
                mem_size_m = max_mem_size_m

        if mem_params.get("vm_mem_minimum"):
            min_mem_size_m = self._params.get("vm_mem_minimum")
            min_mem_size_m = float(normalize_data_size(min_mem_size_m))
            if mem_size_m < min_mem_size_m:
                raise InstanceSpecError(
                    "Guest min memory has to be %s"
                    ", got %s" % (min_mem_size_m, mem_size_m)
                )

        machine["size"] = str(int(mem_size_m))

        maxmem = mem_params.get("maxmem")
        if maxmem:
            machine["max_mem"] = float(normalize_data_size(maxmem, "B"))
            slots = mem_params.get("slots")
            if slots:
                machine["slots"] = slots

        if Flags.MACHINE_MEMORY_BACKEND in self._qemu_caps and not self._params.get(
            "guest_numa_nodes"
        ):
            machine_backend = dict()
            machine_backend["id"] = "mem-machine_mem"
            machine_backend["type"] = self._params.get("vm_mem_backend")

            backend_options = dict()
            backend_options["size_mem"] = "%sM" % mem_params["mem"]
            if self._params.get("vm_mem_policy"):
                backend_options["policy_mem"] = self._params.get("vm_mem_policy")
            if self._params.get("vm_mem_host_nodes"):
                backend_options["host-nodes"] = self._params.get("vm_mem_host_nodes")
            if self._params.get("vm_mem_prealloc"):
                backend_options["prealloc_mem"] = self._params.get("vm_mem_prealloc")
            if self._params.get("vm_mem_backend") == "memory-backend-file":
                if not self._params.get("vm_mem_backend_path"):
                    raise InstanceSpecError(
                        "Missing the vm_mem_backend_path"
                    )
                backend_options["mem-path_mem"] = self._params["vm_mem_backend_path"]
            if self._params.get("hugepage_path"):
                machine_backend["type"] = "memory-backend-file"
                backend_options["mem-path_mem"] = self._params["hugepage_path"]
                backend_options["prealloc_mem"] = self._params.get(
                    "vm_mem_prealloc", "yes"
                )

            backend_options["share_mem"] = self._params.get("vm_mem_share")
            if machine_backend["type"] is None:
                machine_backend["type"] = "memory-backend-ram"
            backend_param = Params(backend_options)
            params = backend_param.object_params("mem")
            attrs = qdevices.Memory.__attributes__[machine_backend["type"]][:]
            machine_backend["props"] = {k: v for k, v in params.copy_from_keys(attrs).items()}
            machine["backend"] = machine_backend
        else:
            if mem_params.get("hugepage_path") and not mem_params.get("guest_nume_node"):
                machine["mem_path"] = mem_params["hugepage_path"]

        return machine

    def _parse_params(self):
        self._spec.update({"machine": self._define_spec()})


class QemuSpecMemoryDevice(QemuSpec):
    def __init__(self, name, vt_params, node, mem_name):
        super(QemuSpecMemoryDevice, self).__init__(name, vt_params, node)
        self._mem_name = mem_name
        # self._mem_dev = dict()
        # self._mem_dev["id"] = ""
        # self._mem_dev["type"] = ""
        # self._mem_dev["bus"] = ""
        # self._mem_dev["props"] = dict()
        #
        # self._mem_dev_backend = dict()
        # self._mem_dev_backend["id"] = ""
        # self._mem_dev_backend["type"] = ""
        # self._mem_dev_backend["props"] = dict()
        #
        # self._mem_dev["backend"] = self._mem_dev_backend
        #
        # self._mem_dev_spec = {
        #     "memory": {
        #         "devices": [self._mem_dev]
        #     }
        # }
        self._parse_params()

    def _define_spec(self):
        device = dict()
        backend = dict()
        name = self._mem_name

        params = self._params.object_params(name)
        _params = params.object_params("mem")
        backend["type"] = _params.setdefault("backend", "memory-backend-ram")
        backend["id"] = "%s-%s" % ("mem", name)
        attrs = qdevices.Memory.__attributes__[backend["type"]][:]
        backend["props"] = {k: v for k, v in _params.copy_from_keys(attrs).items()}
        device["backend"] = backend

        mem_devtype = params.get("vm_memdev_model", "dimm")
        if params.get("use_mem", "yes") == "yes":
            if mem_devtype == "dimm":
                dimm_params = Params()
                suffix = "_dimm"
                for key in list(params.keys()):
                    if key.endswith(suffix):
                        new_key = key.rsplit(suffix)[0]
                        dimm_params[new_key] = params[key]
                dev_type = "nvdimm" if params.get("nv_backend") else "pc-dimm"
                attrs = qdevices.Dimm.__attributes__[dev_type][:]
                dimm_uuid = dimm_params.get("uuid")
                if "uuid" in attrs and dimm_uuid:
                    try:
                        dimm_params["uuid"] = str(uuid.UUID(dimm_uuid))
                    except ValueError:
                        if dimm_uuid == "<auto>":
                            dimm_params["uuid"] = str(
                                uuid.uuid5(uuid.NAMESPACE_OID, name))
                dev_id = "%s-%s" % ("dimm", name)
                dev_bus = None
                dev_props = {k: v for k, v in
                             dimm_params.copy_from_keys(attrs).items()}
                dev_props.update(params.get_dict("dimm_extra_params"))
                dev_props["memdev"] = backend["id"] # FIXME:

            elif mem_devtype == "virtio-mem":
                dev_type = "virtio-mem-pci"
                dev_bus = params.get("pci_bus", "pci.0")
                dev_id = "%s-%s" % ("virtio_mem", name)
                virtio_mem_params = Params()
                suffix = "_memory"
                for key in list(params.keys()):
                    if key.endswith(suffix):
                        new_key = key.rsplit(suffix)[0]
                        virtio_mem_params[new_key] = params[key]
                supported = [
                    "any_layout",
                    "block-size",
                    "dynamic-memslots",
                    "event_idx",
                    "indirect_desc",
                    "iommu_platform",
                    "memaddr",
                    "memdev",
                    "node",
                    "notify_on_empty",
                    "packed",
                    "prealloc",
                    "requested-size",
                    "size",
                    "unplugged-inaccessible",
                    "use-disabled-flag",
                    "use-started",
                    "x-disable-legacy-check",
                ]
                dev_props = {k: v for k, v in virtio_mem_params.copy_from_keys(
                    supported).items()}
                if "-mmio:" in params.get("machine_type"):
                    dev_type = "virtio-mem-device"
                    dev_bus = None
                    dev_props = {}
                if not self._has_device(dev_type):
                    raise InstanceSpecError(
                        "%s device is not available" % dev_type
                    )
            else:
                raise InstanceSpecError("Unsupported memory device type")

            device["type"] = dev_type
            device["id"] = dev_id
            device["bus"] = dev_bus
            device["props"] = dev_props

        return device

        # self._mem_dev.update(device)
        # self._mem_dev_backend.update(backend)

    def _parse_params(self):
        self._spec.update({"memory": {"devices": [self._define_spec()]}})


class QemuSpecMemory(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecMemory, self).__init__(name, vt_params, node)
        self._memory_machine = None
        self._memory_devices = []
        # self._mem_spec = {
        #     "machine": {},
        #     "devices": []
        # }
        self._parse_params()

    def insert_spec(self, spec):
        if isinstance(spec, QemuSpecMemoryDevice):
            self._memory_devices.append(spec)
            self._spec["memory"]["devices"].append(spec.spec["memory"]["devices"][0])
        else:
            raise InstanceSpecError("Unsupported spec type")

    def remove_spec(self, spec):
        self._memory_devices.remove(spec)
        self._spec["memory"]["devices"].remove(spec.spec["memory"]["devices"][0])

    def _define_spec(self):
        self._memory_machine = QemuSpecMemoryMachine(self._name,
                                                     self._params,
                                                     self._node.tag)
        # self._mem_spec["machine"] = self._memory_machine.spec.get("machine")

        for name in self._params.objects("mem_devs"):
            self._memory_devices.append(QemuSpecMemoryDevice(self._name,
                                                             self._params,
                                                             self._node.tag,
                                                             name))

    def _parse_params(self):
        self._define_spec()
        # memory = {}
        # memory.update(self._memory_machine._parse_params())
        # for dev in self._memory_devices:
        #     dev._parse_params()
        # memory["devices"] = [dev._mem_dev for dev in self._memory_devices]
        devices = []
        machine = self._memory_machine.spec.get("machine")
        for spec in self._memory_devices:
            devices.append(spec.spec["memory"]["devices"][0])
        self._spec.update({"memory": {"machine": machine, "devices": devices}})
