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
import logging
import re

from functools import reduce
from operator import mul

from virttest.qemu_capabilities import Flags
from virttest.utils_version import VersionInterval

from ..qemu_specs.spec import QemuSpec
from virttest.vt_vmm.objects.exceptions.instance_exception import InstanceSpecError


try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecCPUInfo(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecCPUInfo, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        cpu_info = dict()
        #  FIXME:
        if self._params.get("auto_cpu_model") == "yes" and self._params.get("vm_type") == "qemu":
            # policy_map = {
            #     "libvirt_host_model": cpu_utils.get_cpu_info_from_virsh,
            #     "virttest": cpu_utils.get_qemu_best_cpu_info,
            # }
            auto_cpu_policy = self._params.get("auto_cpu_policy", "virttest").split()
            for policy in auto_cpu_policy:
                try:
                    cpu_info = None
                    if policy == "virttest":
                        qemu_binary = self._params.get("qemu_binary", "qemu")
                        cpu_info = self._node.proxy.virt.cpu.get_qemu_best_cpu_info(
                            qemu_binary, self._params.get("default_cpu_model", None))
                        if cpu_info:
                            break
                    if policy == "libvirt_host_model":
                        cpu_info = self._node.proxy.virt.cpu.get_cpu_info_from_virsh(
                            self._params["vm_arch_name"], self._params.get("machine_type"))
                        if cpu_info:
                            break
                except Exception as err:
                    LOG.error("Failed to get cpu info with policy %s: %s" % (
                    policy, err))
                    continue
            else:
                raise InstanceSpecError(
                    "Failed to get cpu info with " "policy %s" % auto_cpu_policy
                )

            self._params["cpu_model"] = cpu_info["model"]
            if cpu_info["flags"]:
                cpu_flags = self._params.get("cpu_model_flags")
                self._params["cpu_model_flags"] = self._node.proxy.virt.cpu.recombine_qemu_cpu_flags(
                    cpu_info["flags"], cpu_flags
                )

        cpu_model = self._params.get("cpu_model", "")
        support_cpu_model = self._node.proxy.virt.tools.qemu.get_help_info(
            "-cpu ", self._qemu_binary)
        use_default_cpu_model = True
        if cpu_model:
            use_default_cpu_model = False
            for model in re.split(",", cpu_model):
                model = model.strip()
                if model not in support_cpu_model:
                    continue
                cpu_model = model
                break
            else:
                cpu_model = model
                LOG.error(
                    "Non existing CPU model %s will be passed "
                    "to qemu (wrong config or negative test)",
                    model,
                )

        if use_default_cpu_model:
            cpu_model = self._params.get("default_cpu_model", "")

        if cpu_model:
            family = self._params.get("cpu_family", "")
            flags = self._params.get("cpu_model_flags", "")
            vendor = self._params.get("cpu_model_vendor", "")
            self._cpuinfo.model = cpu_model
            self._cpuinfo.vendor = vendor
            self._cpuinfo.flags = flags
            self._cpuinfo.family = family
            cpu_driver = self._params.get("cpu_driver")
            if cpu_driver:
                try:
                    cpu_driver_items = cpu_driver.split("-")
                    ctype = cpu_driver_items[cpu_driver_items.index("cpu") - 1]
                    self._cpuinfo.qemu_type = ctype
                except ValueError:
                    LOG.warning("Can not assign cpuinfo.type, assign as" " 'unknown'")
                    self._cpuinfo.qemu_type = "unknown"

            cpu_info["model"] = cpu_model
            cpu_info["family"] = family
            cpu_info["flags"] = flags
            cpu_info["vendor"] = vendor

            if not self._has_option("cpu"):
                cpu_info = {}

            # CPU flag 'erms' is required by Win10 and Win2016 guest, if VM's
            # CPU model is 'Penryn' or 'Nehalem'(see detail RHBZ#1252134), and
            # it's harmless for other guest, so add it here.
            if cpu_model in ["Penryn", "Nehalem"]:
                cpu_help_info = self._node.proxy.virt.tools.qemu.get_help_info("-cpu ", self._qemu_binary)
                match = re.search("Recognized CPUID flags:(.*)", cpu_help_info,
                                  re.M | re.S)
                try:
                    recognize_flags = list(filter(None, re.split("\s", match.group(1))))
                except AttributeError:
                    recognize_flags = []
                if not ("erms" in flags or "erms" in recognize_flags):
                    flags += ",+erms"
                    cpu_info["flags"] = flags
        return cpu_info

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecCPUTopology(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecCPUTopology, self).__init__(name, vt_params, node)
        self._cpu_info = QemuSpecCPUInfo(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        cpu_model = self._cpu_info.spec.get("model")
        cpu_topology = dict()
        # Add smp
        smp = self._params.get_numeric("smp")
        vcpu_maxcpus = self._params.get_numeric("vcpu_maxcpus")
        vcpu_sockets = self._params.get_numeric("vcpu_sockets")
        win_max_vcpu_sockets = self._params.get_numeric("win_max_vcpu_sockets", 2)
        vcpu_cores = self._params.get_numeric("vcpu_cores")
        vcpu_threads = self._params.get_numeric("vcpu_threads")
        vcpu_dies = self._params.get("vcpu_dies", 0)
        enable_dies = vcpu_dies != "INVALID" and Flags.SMP_DIES in self._qemu_caps
        vcpu_clusters = self._params.get("vcpu_clusters", 0)
        enable_clusters = (
            vcpu_clusters != "INVALID" and Flags.SMP_CLUSTERS in self._qemu_caps
        )
        vcpu_drawers = self._params.get("vcpu_drawers", 0)
        enable_drawers = vcpu_drawers != "INVALID" and Flags.SMP_DRAWERS in self._qemu_caps
        vcpu_books = self._params.get("vcpu_books", 0)
        enable_books = vcpu_books != "INVALID" and Flags.SMP_BOOKS in self._qemu_caps

        if not enable_dies:
            # Set dies=1 when computing missing values
            vcpu_dies = 1
        # PC target support SMP 'dies' parameter since qemu 4.1
        vcpu_dies = int(vcpu_dies)

        if not enable_clusters:
            # Set clusters=1 when computing missing values
            vcpu_clusters = 1
        # ARM target support SMP 'clusters' parameter since qemu 7.0
        vcpu_clusters = int(vcpu_clusters)

        if not enable_drawers:
            # Set drawers=1 when computing missing values
            vcpu_drawers = 1
        # s390x target support SMP 'drawers' parameter since qemu 8.2
        vcpu_drawers = int(vcpu_drawers)

        if not enable_books:
            # Set books=1 when computing missing values
            vcpu_books = 1
        # s390x target support SMP 'books' parameter since qemu 8.2
        vcpu_books = int(vcpu_books)

        # Some versions of windows don't support more than 2 sockets of cpu,
        # here is a workaround to make all windows use only 2 sockets.
        if (
            vcpu_sockets
            and self._params.get("os_type") == "windows"
            and vcpu_sockets > win_max_vcpu_sockets
        ):
            vcpu_sockets = win_max_vcpu_sockets

        amd_vendor_string = self._params.get("amd_vendor_string")
        if not amd_vendor_string:
            amd_vendor_string = "AuthenticAMD"
        if amd_vendor_string == self._node.proxy.cpu.get_cpu_vendor_id():
            # AMD cpu do not support multi threads besides EPYC
            if self._params.get(
                "test_negative_thread", "no"
            ) != "yes" and not cpu_model.startswith("EPYC"):
                vcpu_threads = 1
                txt = "Set vcpu_threads to 1 for AMD non-EPYC cpu."
                LOG.warning(txt)

        smp_err = ""
        SMP_PREFER_CORES_VERSION_SCOPE = "[6.2.0, )"
        #  In the calculation of omitted sockets/cores/threads: we prefer
        #  sockets over cores over threads before 6.2, while preferring
        #  cores over sockets over threads since 6.2.
        vcpu_prefer_sockets = self._params.get("vcpu_prefer_sockets")
        if vcpu_prefer_sockets:
            vcpu_prefer_sockets = self._params.get_boolean("vcpu_prefer_sockets")
        else:
            if self._qemu_ver not in VersionInterval(SMP_PREFER_CORES_VERSION_SCOPE):
                # Prefer sockets over cores before 6.2
                vcpu_prefer_sockets = True
            else:
                vcpu_prefer_sockets = False

        if vcpu_maxcpus != 0:
            smp_values = [
                vcpu_drawers,
                vcpu_books,
                vcpu_sockets,
                vcpu_dies,
                vcpu_clusters,
                vcpu_cores,
                vcpu_threads,
            ]
            if smp_values.count(0) == 1:
                smp_values.remove(0)
                topology_product = reduce(mul, smp_values)
                if vcpu_maxcpus < topology_product:
                    smp_err = (
                        "maxcpus(%d) must be equal to or greater than "
                        "topological product(%d)" % (vcpu_maxcpus, topology_product)
                    )
                else:
                    missing_value, cpu_mod = divmod(vcpu_maxcpus, topology_product)
                    vcpu_maxcpus -= cpu_mod
                    vcpu_drawers = vcpu_drawers or missing_value
                    vcpu_books = vcpu_books or missing_value
                    vcpu_sockets = vcpu_sockets or missing_value
                    vcpu_dies = vcpu_dies or missing_value
                    vcpu_clusters = vcpu_clusters or missing_value
                    vcpu_cores = vcpu_cores or missing_value
                    vcpu_threads = vcpu_threads or missing_value
            elif smp_values.count(0) > 1:
                if vcpu_maxcpus == 1 and max(smp_values) < 2:
                    vcpu_drawers = (
                        vcpu_books
                    ) = (
                        vcpu_sockets
                    ) = vcpu_dies = vcpu_clusters = vcpu_cores = vcpu_threads = 1

            hotpluggable_cpus = len(self._params.objects("vcpu_devices"))
            if self._params["machine_type"].startswith("pseries"):
                hotpluggable_cpus *= vcpu_threads
            smp = smp or vcpu_maxcpus - hotpluggable_cpus
        else:
            vcpu_drawers = vcpu_drawers or 1
            vcpu_books = vcpu_books or 1
            vcpu_dies = vcpu_dies or 1
            vcpu_clusters = vcpu_clusters or 1
            if smp == 0:
                vcpu_sockets = vcpu_sockets or 1
                vcpu_cores = vcpu_cores or 1
                vcpu_threads = vcpu_threads or 1
            else:
                if vcpu_prefer_sockets:
                    if vcpu_sockets == 0:
                        vcpu_cores = vcpu_cores or 1
                        vcpu_threads = vcpu_threads or 1
                        vcpu_sockets = (
                            smp
                            // (
                                vcpu_cores
                                * vcpu_threads
                                * vcpu_clusters
                                * vcpu_dies
                                * vcpu_drawers
                                * vcpu_books
                            )
                            or 1
                        )
                    elif vcpu_cores == 0:
                        vcpu_threads = vcpu_threads or 1
                        vcpu_cores = (
                            smp
                            // (
                                vcpu_sockets
                                * vcpu_threads
                                * vcpu_clusters
                                * vcpu_dies
                                * vcpu_drawers
                                * vcpu_books
                            )
                            or 1
                        )
                else:
                    # Prefer cores over sockets since 6.2
                    if vcpu_cores == 0:
                        vcpu_sockets = vcpu_sockets or 1
                        vcpu_threads = vcpu_threads or 1
                        vcpu_cores = (
                            smp
                            // (
                                vcpu_sockets
                                * vcpu_threads
                                * vcpu_clusters
                                * vcpu_dies
                                * vcpu_drawers
                                * vcpu_books
                            )
                            or 1
                        )
                    elif vcpu_sockets == 0:
                        vcpu_threads = vcpu_threads or 1
                        vcpu_sockets = (
                            smp
                            // (
                                vcpu_cores
                                * vcpu_threads
                                * vcpu_clusters
                                * vcpu_dies
                                * vcpu_drawers
                                * vcpu_books
                            )
                            or 1
                        )

                if vcpu_threads == 0:
                    # Try to calculate omitted threads at last
                    vcpu_threads = (
                        smp
                        // (
                            vcpu_cores
                            * vcpu_sockets
                            * vcpu_clusters
                            * vcpu_dies
                            * vcpu_drawers
                            * vcpu_books
                        )
                        or 1
                    )

            smp = (
                smp
                or vcpu_sockets
                * vcpu_dies
                * vcpu_clusters
                * vcpu_cores
                * vcpu_threads
                * vcpu_drawers
                * vcpu_books
            )

            hotpluggable_cpus = len(self._params.objects("vcpu_devices"))
            if self._params["machine_type"].startswith("pseries"):
                hotpluggable_cpus *= vcpu_threads
            vcpu_maxcpus = smp
            smp -= hotpluggable_cpus

        if smp <= 0:
            smp_err = (
                "Number of hotpluggable vCPUs(%d) is greater "
                "than or equal to the maxcpus(%d)." % (hotpluggable_cpus, vcpu_maxcpus)
            )
        if smp_err:
            raise InstanceSpecError(smp_err)

        self._cpuinfo.smp = smp
        cpu_topology["smp"] = self._cpuinfo.smp
        smp_pattern = "smp .*\[,maxcpus=.*\].*"
        if self._has_option(smp_pattern):
            self._cpuinfo.maxcpus = vcpu_maxcpus
        cpu_topology["maxcpus"] = self._cpuinfo.maxcpus

        self._cpuinfo.cores = vcpu_cores
        if self._cpuinfo.cores != 0:
            cpu_topology["cores"] = self._cpuinfo.cores

        self._cpuinfo.threads = vcpu_threads
        if self._cpuinfo.threads != 0:
            cpu_topology["threads"] = self._cpuinfo.threads

        self._cpuinfo.sockets = vcpu_sockets
        if self._cpuinfo.sockets != 0:
            cpu_topology["sockets"] = self._cpuinfo.sockets

        if enable_dies:
            self._cpuinfo.dies = vcpu_dies
        if self._cpuinfo.dies != 0:
            cpu_topology["dies"] = self._cpuinfo.dies

        if enable_clusters:
            self._cpuinfo.clusters = vcpu_clusters
        if self._cpuinfo.clusters != 0:
            cpu_topology["clusters"] = self._cpuinfo.clusters

        if enable_drawers:
            self._cpuinfo.drawers = vcpu_drawers
        if self._cpuinfo.drawers != 0:
            cpu_topology["drawers"] = self._cpuinfo.drawers

        if enable_books:
            self._cpuinfo.books = vcpu_books
        if self._cpuinfo.books != 0:
            cpu_topology["books"] = self._cpuinfo.books

        return cpu_topology

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecCPUDevice(QemuSpec):
    def __init__(self, name, vt_params, node, vcpu_name):
        super(QemuSpecCPUDevice, self).__init__(name, vt_params, node)
        self._vcpu_name = vcpu_name
        self._parse_params()

    def _define_spec(self):
        cpu_device = {}
        # Add vcpu devices
        # TODO: support it in the future since did not get the purpose of the following code
        # vcpu_bus = devices.get_buses({"aobject": "vcpu"})
        # if vcpu_bus and params.get("vcpu_devices"):
        #     vcpu_bus = vcpu_bus[0]
        #     vcpu_bus.initialize(self._cpuinfo)
        #     vcpu_devices = params.objects("vcpu_devices")
        #     params["vcpus_count"] = str(vcpu_bus.vcpus_count)

        params = self._params.object_params(self._vcpu_name)
        cpu_device["id"] = params.get("vcpu_id", self._vcpu_name)
        cpu_driver = params.get("cpu_driver")
        if not self._has_device(cpu_driver):
            raise InstanceSpecError("Unsupport cpu driver %s" % cpu_driver)
        cpu_device["type"] = cpu_driver
        cpu_device["props"] = json.loads(params.get("vcpu_props", "{}"))
        cpu_device["enable"] = params.get_boolean("vcpu_enable")
        cpu_device["bus"] = "vcpu"
        return cpu_device

    def _parse_params(self):
        self._spec.update({"cpu": {"devices": [self._define_spec()]}})


class QemuSpecCPU(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecCPU, self).__init__(name, vt_params, node)
        self._cpu_info = None
        self._cpu_topology = None
        self._cpu_devices = []
        self._parse_params()

    def _define_spec(self):
        self._cpu_info = QemuSpecCPUInfo(self._name, self._params, self._node.tag,)
        self._cpu_topology = QemuSpecCPUTopology(self._name, self._params, self._node.tag,)
        for vcpu_name in self._params.objects("vcpu_devices"):
            self._cpu_devices.append(QemuSpecCPUDevice(self._name, self._params,
                                                       self._node.tag, vcpu_name))

    def insert_device(self, spec):
        raise NotImplementedError

    def remove_device(self, spec):
        raise NotImplementedError

    def _parse_params(self):
        self._define_spec()
        info = self._cpu_info.spec
        topology = self._cpu_topology.spec
        devices = []
        for cpu_device in self._cpu_devices:
            devices.append(cpu_device.spec["cpu"]["devices"][0])
        self._spec.update({"cpu": {"info": info, "topology": topology, "devices": devices}})
