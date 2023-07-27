import json
import logging
import re
import uuid

import six

from virttest import arch, storage, utils_misc
from virttest.qemu_devices import qdevices
from virttest.utils_params import Params

try:
    from virttest.vt_imgr import vt_imgr
except ImportError:
    pass

from ..objects import instance_spec

LOG = logging.getLogger("avocado." + __name__)


class QemuSpec(instance_spec.Spec):
    def __init__(self, name, vt_params):
        super(QemuSpec, self).__init__(name, "qemu", vt_params)
        # self._params = None

    def _get_bus(self, params, dtype=None, pcie=False):
        """
        Deal with different buses for multi-arch
        """
        if params.get("machine_type").startswith("s390"):
            return self._get_ccw_bus()
        else:
            return self._get_pci_bus(params, dtype, pcie)

    @staticmethod
    def _get_ccw_bus():
        """
        Get device parent bus for s390x
        """
        return "virtual-css"

    @staticmethod
    def _get_pci_bus(params, dtype=None, pcie=False):
        """
        Get device parent pci bus by dtype

        :param params: test params for the device
        :param dtype: device type like, 'nic', 'disk',
                      'vio_rng', 'vio_port' or 'cdrom'
        :param pcie: it's a pcie device or not (bool type)

        :return: return bus
        """
        machine_type = params.get("machine_type", "")
        if "mmio" in machine_type:
            return None
        if dtype and "%s_pci_bus" % dtype in params:
            return params["%s_pci_bus" % dtype]
        if machine_type == "q35" and not pcie:
            return "q35-pci-bridge"
        return params.get("pci_bus", "pci.0")

    def _define_spec_name(self):
        return self._name

    def _define_spec_uuid(self):
        """
        Define the specification of the uuid


        :return: uuid
        :rtype: str
        """
        return self._params.get("uuid")

    def _define_spec_preconfig(self):
        """
        Define the specification to pause QEMU for interactive configuration
        before the machine is created, which allows querying and configuring
        properties that will affect machine initialization.

        :return: True or False
        :rtype: bool
        """
        return self._params.get_boolean("qemu_preconfig")

    def _define_spec_sandbox(self):
        """
        Define the specification of the sandbox

        :return: The specification of the sandbox.
                 Schema format: {"action": str, "props": dict}
        :rtype: dict
        """
        sandbox = dict()
        action = self._params.get("qemu_sandbox")
        sandbox["action"] = action

        props = {
            "elevateprivileges": self._params.get("qemu_sandbox_elevateprivileges"),
            "obsolete": self._params.get("qemu_sandbox_obsolete"),
            "resourcecontrol": self._params.get("qemu_sandbox_resourcecontrol"),
            "spawn": self._params.get("qemu_sandbox_spawn"),
        }
        sandbox["props"] = props

        return sandbox

    def _define_spec_defaults(self):
        """
        Define the specification of the defaults

        :return: True or False
        :rtype: bool
        :raise: ValueError
        """
        defaults = self._params.get("defaults", "no")
        if defaults == "yes":
            return True
        elif defaults == "no":
            return False
        else:
            raise ValueError

    def _define_spec_machine(self):
        """
        Define the specification of the machine.

        :return: The specification of the machine.
                 Schema format: {
                                    "type": str,
                                    "accel": str,
                                    "hpet": bool,
                                    "props": dict,
                                }
        :rtype: dict
        """
        machine = dict()
        machine_props = dict()
        machine["type"] = self._params.get("machine_type")

        if self._params.get("invalid_machine_type", "no") == "yes":
            machine["type"] = "invalid"

        machine["accel"] = self._params.get("vm_accelerator")
        if self._params.get("disable_hpet") == "yes":
            machine["hpet"] = False
        elif self._params.get("disable_hpet") == "no":
            machine["hpet"] = True

        machine_type_extra_params = self._params.get("machine_type_extra_params", "")
        for keypair_str in machine_type_extra_params.split(","):
            if not keypair_str:
                continue
            keypair = keypair_str.split("=", 1)
            if len(keypair) < 2:
                keypair.append("NO_EQUAL_STRING")
            machine_props[keypair[0]] = keypair[1]

        machine["props"] = machine_props

        return machine

    def _define_spec_launch_security(self):
        """
        Define the specification of the launch security

        :return: The specification of the launch security.
                 Schema format: {"type": str, "id": str, "props": dict}
        :rtype: dict
        """
        launch_security = dict()

        vm_secure_guest_type = self._params.get("vm_secure_guest_type")
        if vm_secure_guest_type:
            launch_security["id"] = "lsec0"
            security_props = dict()

            if vm_secure_guest_type == "sev":
                launch_security["type"] = "sev-guest"
                security_props["policy"] = int(self._params.get("vm_sev_policy", 3))
                security_props["cbitpos"] = int(self._params["vm_sev_cbitpos"])
                security_props["reduced_phys_bits"] = int(
                    self._params["vm_sev_reduced_phys_bits"]
                )

                if self._params.get("vm_sev_session_file"):
                    security_props["session-file"] = self._params["vm_sev_session_file"]
                if self._params.get("vm_sev_dh_cert_file"):
                    security_props["dh-cert-file"] = self._params["vm_sev_dh_cert_file"]

                if self._params.get("vm_sev_kernel_hashes"):
                    security_props["kernel-hashes"] = self._params.get_boolean(
                        "vm_sev_kernel_hashes"
                    )

            elif vm_secure_guest_type == "tdx":
                launch_security["type"] = "tdx-guest"
            else:
                raise ValueError

            launch_security["props"] = security_props

        return launch_security

    def _define_spec_iommu(self):
        """
        Define the specification of the iommu

        :return: The specification of the iommu.
                 Schema format: {"type": str, "bus": str, "props": dict}
        :rtype: dict
        """
        iommu = dict()
        iommu_props = dict()

        if self._params.get("intel_iommu"):
            iommu["type"] = "intel_iommu"
            iommu_props["intremap"] = self._params.get("iommu_intremap", "on")
            iommu_props["device_iotlb"] = self._params.get("iommu_device_iotlb", "on")
            iommu_props["caching_mode"] = self._params.get("iommu_caching_mode")
            iommu_props["eim"] = self._params.get("iommu_eim")
            iommu_props["x_buggy_eim"] = self._params.get("iommu_x_buggy_eim")
            iommu_props["version"] = self._params.get("iommu_version")
            iommu_props["x_scalable_mode"] = self._params.get("iommu_x_scalable_mode")
            iommu_props["dma_drain"] = self._params.get("iommu_dma_drain")
            iommu_props["pt"] = self._params.get("iommu_pt")
            iommu_props["aw_bits"] = self._params.get("iommu_aw_bits")
            iommu["props"] = iommu_props

        elif self._params.get("virtio_iommu"):
            iommu["type"] = "virtio_iommu"
            iommu["bus"] = "pci.0"
            iommu_props["pcie_direct_plug"] = "yes"
            virtio_iommu_extra_params = self._params.get("virtio_iommu_extra_params")
            if virtio_iommu_extra_params:
                for extra_param in virtio_iommu_extra_params.strip(",").split(","):
                    key, value = extra_param.split("=")
                    iommu_props[key] = value
            iommu["props"] = iommu_props

        return iommu

    def _define_spec_vga(self):
        """
        Define the specification of the VGA(Video Graphics Array)

        :return: The specification of the VGA.
                 Schema format: {"type": str, "bus": str}
        :rtype: dict
        """
        vga = dict()

        if self._params.get("vga"):
            vga["type"] = self._params.get("vga")

            machine_type = self._params.get("machine_type", "")
            pcie = machine_type.startswith("q35") or machine_type.startswith(
                "arm64-pci"
            )
            vga["bus"] = self._get_bus(self._params, "vga", pcie)

        return vga

    def _define_spec_watchdog(self):
        """
        Define the specification of the watch dog

        :return: The specification of the watch dog.
                 Schema format: {"type": str, "bus": str, "action": str}
        :rtype: dict
        """
        watchdog = dict()

        if self._params.get("enable_watchdog", "no") == "yes":
            watchdog["type"] = self._params.get("watchdog_device_type")
            watchdog["bus"] = self._get_pci_bus(self._params, None, False)
            watchdog["action"] = self._params.get("watchdog_action", "reset")

        return watchdog

    def _define_spec_pci_controllers(self):
        """
        Define the specification of the PCI controllers

        :return: The specification of the PCI controllers.
                 Schema format: [{"type": str, "id": str, "bus": str}]
        :rtype: list
        """

        pci_controllers = []

        for pcic in self._params.objects("pci_controllers"):
            pci_controller = dict()
            pcic_params = self._params.object_params(pcic)
            pci_controller["type"] = pcic_params.get("type", "pcie-root-port")
            pci_controller["id"] = pcic
            pci_controller["bus"] = pcic_params.get("pci_bus")
            pci_controllers.append(pci_controller)

        return pci_controllers

    def _define_spec_memory(self):
        """
        Define the specification of the memory

        :return: The specification of the memory.
                 Schema format:
                    {
                        "machine": {
                                    "size": int(bytes),
                                    "slots": int,
                                    "max_mem": int(bytes),
                                    "mem_path": str,
                                    "backend":{
                                                "type": str,
                                                "id": str
                                                "props": dict,
                                                },
                                    },
                        "backends": [
                                        {
                                        "type": str,
                                        "id": str,
                                        "props": dict,
                                        },
                                    ],
                        "devices": [
                                        {
                                        "type": str,
                                        "id": str,
                                        "bus": str,
                                        "props": dict,
                                        },
                                    ]
                    }
        :rtype: dict
        """
        memory = {}

        machine = dict()
        normalize_data_size = utils_misc.normalize_data_size
        mem = self._params.get("mem", None)
        mem_params = self._params.object_params("mem")
        if mem:
            mem_size_m = "%sM" % mem_params["mem"]
            mem_size_m = float(normalize_data_size(mem_size_m))
            machine["size"] = str(int(mem_size_m))

        maxmem = mem_params.get("maxmem")
        if maxmem:
            machine["max_mem"] = float(normalize_data_size(maxmem, "B"))
            slots = mem_params.get("slots")
            if slots:
                machine["slots"] = slots

        machine_backend = dict()
        machine_backend["type"] = self._params.get("vm_mem_backend")
        machine_backend["id"] = "mem-machine_mem"
        backend_props = dict()
        backend_props["size"] = "%sM" % mem_params["mem"]
        if self._params.get("vm_mem_policy"):
            backend_props["policy_mem"] = self._params.get("vm_mem_policy")
        if self._params.get("vm_mem_host_nodes"):
            backend_props["host-nodes"] = self._params.get("vm_mem_host_nodes")
        if self._params.get("vm_mem_prealloc"):
            backend_props["prealloc_mem"] = self._params.get("vm_mem_prealloc")
        if self._params.get("vm_mem_backend_path"):
            backend_props["mem-path_mem"] = self._params.get("vm_mem_backend_path")
        if self._params.get("vm_mem_share"):
            backend_props["mem-share_mem"] = self._params.get("vm_mem_share")
        machine_backend["props"] = backend_props
        machine["backend"] = machine_backend

        if mem_params.get("hugepage_path") and not mem_params.get("guest_nume_node"):
            machine["mem_path"] = mem_params["hugepage_path"]

        devices = []
        dev_backends = []
        for name in self._params.objects("mem_devs"):
            device = dict()
            backend = dict()

            params = self._params.object_params(name)
            dev_type = params.get("vm_memdev_model", "dimm")
            mem_params = params.object_params("mem")
            mem_params.setdefault("backend", "memory-backend-ram")
            attrs = qdevices.Memory.__attributes__[mem_params["backend"]][:]
            backend["type"] = mem_params["backend"]
            backend["id"] = f"mem-{name}"
            backend["props"] = mem_params.copy_from_keys(attrs)
            dev_backends.append(backend)

            device["type"] = dev_type
            device["bus"] = params.get("pci_bus")

            use_mem = params.object_params(name).get("use_mem", "yes")
            if use_mem:
                if device.get("type") == "dimm":
                    dimm_props = dict()
                    device["id"] = f"dimm-{name}"
                    dimm_params = Params()
                    suffix = "_dimm"
                    for key in list(params.keys()):
                        if key.endswith(suffix):
                            new_key = key.rsplit(suffix)[0]
                            dimm_params[new_key] = params[key]
                    attrs = qdevices.Dimm.__attributes__[device["type"]][:]
                    dimm_uuid = dimm_params.get("uuid")
                    if "uuid" in attrs and dimm_uuid:
                        try:
                            dimm_props["uuid"] = str(uuid.UUID(dimm_uuid))
                        except ValueError:
                            if dimm_uuid == "<auto>":
                                dimm_props["uuid"] = str(
                                    uuid.uuid5(uuid.NAMESPACE_OID, name)
                                )
                    dimm_props.update(dimm_params.copy_from_keys(attrs))
                    dimm_props["backend"] = backend["id"]
                    device["props"] = dimm_props

                elif device.get("type") == "virtio-mem":
                    virtio_mem_props = dict()
                    virtio_mem_params = Params()
                    device["bus"] = params.get("pci_bus", "pci.0")
                    suffix = "_memory"
                    for key in list(params.keys()):
                        if key.endswith(suffix):
                            new_key = key.rsplit(suffix)[0]
                            virtio_mem_params[new_key] = params[key]
                    supported = [
                        "any_layout",
                        "block-size",
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
                    virtio_mem_props.update(virtio_mem_params.copy_from_keys(supported))
                    device["id"] = f"virtio_mem-{name}"
                    device["props"] = virtio_mem_props
                else:
                    raise ValueError

            device["backends"] = dev_backends
            devices.append(device)

        memory["machine"] = machine
        memory["devices"] = devices
        return memory

    def _define_spec_cpu(self):
        """
        Define the specification of the CPU

        :return: The specification of the CPU.
                 Schema format:
                    {
                        "info": {
                                "mode": str,
                                "flags": str,
                                "vendor": str,
                                "family": str,
                                },
                        "topology": {
                                    "smp": int,
                                    "max_cpus": int,
                                    "sockets": int,
                                    "cores": int,
                                    "threads": int,
                                    "dies": int,
                                    "clusters": int,
                                    "prefer": str,
                                    },
                        "devices": [
                                        {
                                        "id": str,
                                        "bus": str,
                                        "enable": bool,
                                        "props": dict,
                                        },
                                    ]
                    }
        :rtype: dict
        """
        cpu = {}
        cpu_info = dict()
        cpu_topology = dict()
        cpu_devices = []
        cpu_device = dict()

        cpu_model = self._params.get("cpu_model", "")
        use_default_cpu_model = True

        # support_cpu_model = to_text(process.run("%s -cpu \\?" % qemu_binary,
        #                                         verbose=False,
        #                                         ignore_status=True,
        #                                         shell=True).stdout,
        #                             errors='replace')

        # if cpu_model:
        #     use_default_cpu_model = False
        #     for model in re.split(",", cpu_model):
        #         model = model.strip()
        #         if model not in support_cpu_model:
        #             continue
        #         cpu_model = model
        #         break
        #     else:
        #         cpu_model = model
        #         LOG.error(
        #             "Non existing CPU model %s will be passed "
        #             "to qemu (wrong config or negative test)",
        #             model,
        #         )
        #
        # if use_default_cpu_model:
        #     cpu_model = self._params.get("default_cpu_model", "")

        if cpu_model:
            cpu_info["model"] = cpu_model
            cpu_info["family"] = self._params.get("cpu_family", "")
            cpu_info["flags"] = self._params.get("cpu_model_flags", "")
            cpu_info["vendor"] = self._params.get("cpu_model_vendor", "")

        smp = self._params.get_numeric("smp")
        vcpu_maxcpus = self._params.get_numeric("vcpu_maxcpus")
        vcpu_sockets = self._params.get_numeric("vcpu_sockets")
        win_max_vcpu_sockets = self._params.get_numeric("win_max_vcpu_sockets", 2)
        vcpu_cores = self._params.get_numeric("vcpu_cores")
        vcpu_threads = self._params.get_numeric("vcpu_threads")
        vcpu_dies = self._params.get("vcpu_dies", 0)
        vcpu_clusters = self._params.get("vcpu_clusters", 0)
        vcpu_drawers = self._params.get("vcpu_drawers", 0)
        vcpu_books = self._params.get("vcpu_books", 0)

        # Some versions of windows don't support more than 2 sockets of cpu,
        # here is a workaround to make all windows use only 2 sockets.
        if (
                vcpu_sockets
                and self._params.get("os_type") == "windows"
                and vcpu_sockets > win_max_vcpu_sockets

        ):
            vcpu_sockets = win_max_vcpu_sockets

        cpu_topology["smp"] = smp
        cpu_topology["max_cpus"] = vcpu_maxcpus
        cpu_topology["sockets"] = vcpu_sockets
        cpu_topology["cores"] = vcpu_cores
        cpu_topology["threads"] = vcpu_threads

        cpu_topology["dies"] = vcpu_dies
        if vcpu_dies != "INVALID":
            cpu_topology["dies"] = int(vcpu_dies)

        cpu_topology["clusters"] = vcpu_clusters
        if vcpu_clusters != "INVALID":
            cpu_topology["clusters"] = int(vcpu_clusters)

        cpu_topology["drawers"] = vcpu_drawers
        if vcpu_drawers != "INVALID":
            cpu_topology["drawers"] = int(vcpu_drawers)

        cpu_topology["books"] = vcpu_books
        if vcpu_books != "INVALID":
            cpu_topology["books"] = int(vcpu_books)

        vcpu_prefer_sockets = self._params.get("vcpu_prefer_sockets")
        if vcpu_prefer_sockets and self._params.get_boolean("vcpu_prefer_sockets"):
            cpu_topology["prefer"] = "sockets"

        for vcpu_name in self._params.objects("vcpu_devices"):
            params = self._params.object_params(vcpu_name)
            cpu_device["id"] = params.get("vcpu_id", vcpu_name)
            cpu_device["props"] = json.loads(params.get("vcpu_props", "{}"))
            cpu_device["enable"] = params.get_boolean("vcpu_enable")
            cpu_device["bus"] = "vcpu"
            cpu_devices.append(cpu_device)

        cpu["info"] = cpu_info
        cpu["topology"] = cpu_topology
        cpu["devices"] = cpu_devices

        return cpu

    def _define_spec_numa(self):
        """
        Define the specification of the NUMA

        :return: The specification of the NUMA.
                 Schema format:
                    [
                    ]
        :rtype: list
        """
        numa = []
        return numa

    def _define_spec_soundcards(self):
        """
        Define the specification of the sound card

        :return: The specification of the sound card.
                 Schema format:
                    [
                        {
                        "type": str,
                        "bus": str,
                        }
                    ]
        :rtype: list
        """
        soundcards = []
        if self._params.get("soundcards"):
            for sound_device in self._params.get("soundcards").split(","):
                soundcard = {}
                if "hda" in sound_device:
                    soundcard["type"] = "intel-hba"
                elif sound_device in ("es1370", "ac97"):
                    soundcard["type"] = sound_device.upper()
                else:
                    soundcard["type"] = sound_device

                soundcard["bus"] = self._get_pci_bus(self._params, "soundcard")
                soundcards.append(soundcard)

        return soundcards

    def _define_spec_monitors(self):
        """
        Define the specification of the sound card

        :return: The specification of the sound card.
                 Schema format:
                    [
                        {
                        "id": str,
                        "type": str,
                        "props": dict,
                        "backend": {
                                    "type": str,
                                    "props": dict,
                                    }
                        },
                    ]
        :rtype: list
        """

        monitors = []

        catch_monitor = self._params.get("catch_monitor")
        if catch_monitor:
            if catch_monitor not in self._params.get("monitors"):
                self._params["monitors"] += " %s" % catch_monitor

        for monitor_name in self._params.objects("monitors"):
            monitor = dict()
            monitor_params = self._params.object_params(monitor_name)
            monitor["id"] = monitor_name
            monitor["type"] = monitor_params.get("monitor_type")
            monitor_props = dict()
            monitor_backend = dict()

            chardev_params = self._params.object_params(monitor_name)
            backend = chardev_params.get("chardev_backend", "unix_socket")
            monitor_backend["type"] = backend

            if monitor["type"] == "hmp" and backend != "unix_socket":
                    raise NotImplementedError(
                        "human monitor don't support backend" " %s" % backend
                    )

            monitor_backend_props = dict()
            if backend == "tcp_socket":
                host = chardev_params.get("chardev_host", "127.0.0.1")
                monitor_backend_props["host"] = host
                monitor_backend_props["port"] = (5000, 6000)
                monitor_backend_props["ipv4"] = chardev_params.get(
                    "chardev_ipv4")
                monitor_backend_props["ipv6"] = chardev_params.get(
                    "chardev_ipv6")
                monitor_backend_props["to"] = chardev_params.get("chardev_to")
                monitor_backend_props["server"] = chardev_params.get("chardev_server", "on")
                monitor_backend_props["wait"] = chardev_params.get("chardev_wait", "off")

            elif backend == "udp":
                host = chardev_params.get("chardev_host", "127.0.0.1")
                monitor_backend_props["host"] = host
                monitor_backend_props["port"] = (5000, 6000)
                monitor_backend_props["ipv4"] = chardev_params.get(
                    "chardev_ipv4")
                monitor_backend_props["ipv6"] = chardev_params.get(
                    "chardev_ipv6")

            elif backend == "unix_socket":
                monitor_backend_props["abstract"] = chardev_params.get(
                    "chardev_abstract")
                monitor_backend_props["tight"] = chardev_params.get(
                    "chardev_tight")
                monitor_backend_props["server"] = chardev_params.get("chardev_server", "on")
                monitor_backend_props["wait"] = chardev_params.get("chardev_wait", "off")

            elif backend in ["spicevmc", "spiceport"]:
                monitor_backend_props.update(
                    {
                        "debug": chardev_params.get("chardev_debug"),
                        "name": chardev_params.get("chardev_name"),
                    }
                )
            elif "ringbuf" in backend:
                monitor_backend_props.update(
                    {"ringbuf_write_size": int(
                        chardev_params.get("ringbuf_write_size"))}
                )

            monitor_backend["props"] = monitor_backend_props
            monitor["props"] = monitor_props
            monitor["backend"] = monitor_backend
            monitors.append(monitor)

        return monitors

    def _define_spec_panics(self):
        """
        Define the specification of the panics

        :return: The specification of the panics.
                 Schema format:
                    [
                        {
                        "id": str,
                        "type": str,
                        "props": dict,
                        },
                    ]
        :rtype: list
        """
        panics = []

        if self._params.get("enable_pvpanic") == "yes":
            panic = dict()
            panic_props = dict()
            if "aarch64" in self._params.get("vm_arch_name", arch.ARCH):
                panic["type"] = "pvpanic-pci"
            else:
                panic["type"] = "pvpanic"
                ioport = self._params.get("ioport_pvpanic")
                events = self._params.get("events_pvpanic")
                if ioport:
                    panic_props["ioport"] = ioport
                if events:
                    panic_props["events"] = events
            panic["bus"] = self._get_pci_bus(self._params, None, True)
            panic["props"] = panic_props

        return panics

    def _define_spec_vmcoreinfo(self):
        """
        Define the specification of the VM core info

        :return: The specification of VM core info.
                 Schema format: str
        :rtype: str
        """
        if self._params.get("vmcoreinfo") == "yes":
            return "vmcoreinfo"

    def _define_spec_serials(self):
        """
        Define the specification of the serial consoles

        :return: The specification of the serial consoles.
                 Schema format: [
                    {
                    "id": str,
                    "type": str,
                    "bus": str,
                    "props": dict,
                    "backend": {
                                "type": str,
                                "props": dict,
                            },
                    },
                 ]
        :rtype: list
        """
        serials = []
        for serial_id in self._params.objects("serials"):
            serial = {}
            serial_params = self._params.object_params(serial_id)
            serial["id"] = serial_id
            serial["type"] = serial_params.get("serial_type")
            if serial_params["serial_type"].startswith("pci"):
                serial["bus"] = self._get_pci_bus(serial_params, "serial", False)

            serial_props = {}
            bus_extra_params = serial_params.get("virtio_serial_extra_params", "")
            bus_extra_params = dict([_.split("=") for _ in bus_extra_params.split(",") if _])
            for k, v in bus_extra_params.items():
                serial_props[k] = v

            serial_backend = dict()
            backend = serial_params.get("chardev_backend", "unix_socket")
            serial_backend["type"] = backend

            serial_backend_props = dict()
            serial_backend_props["path"] = serial_params.get("chardev_path")
            if backend == "tcp_socket":
                host = serial_params.get("chardev_host", "127.0.0.1")
                serial_backend_props["host"] = host
                serial_backend_props["port"] = (5000, 5899)
                serial_backend_props["ipv4"] = serial_params.get(
                    "chardev_ipv4")
                serial_backend_props["ipv6"] = serial_params.get(
                    "chardev_ipv6")
                serial_backend_props["to"] = serial_params.get("chardev_to")
                serial_backend_props["server"] = serial_params.get("chardev_server", "on")
                serial_backend_props["wait"] = serial_params.get("chardev_wait", "off")

            elif backend == "udp":
                host = serial_params.get("chardev_host", "127.0.0.1")
                serial_backend_props["host"] = host
                serial_backend_props["port"] = (5000, 5899)
                serial_backend_props["ipv4"] = serial_params.get(
                    "chardev_ipv4")
                serial_backend_props["ipv6"] = serial_params.get(
                    "chardev_ipv6")

            elif backend == "unix_socket":
                serial_backend_props["abstract"] = serial_params.get(
                    "chardev_abstract")
                serial_backend_props["tight"] = serial_params.get(
                    "chardev_tight")
                serial_backend_props["server"] = serial_params.get("chardev_server", "on")
                serial_backend_props["wait"] = serial_params.get("chardev_wait", "off")

            elif backend in ["spicevmc", "spiceport"]:
                serial_backend_props.update(
                    {
                        "debug": serial_params.get("chardev_debug"),
                        "name": serial_params.get("chardev_name"),
                    }
                )
            elif "ringbuf" in backend:
                serial_backend_props.update(
                    {"ringbuf_write_size": int(
                        serial_params.get("ringbuf_write_size"))}
                )
            serial_backend["props"] = serial_backend_props

            prefix = serial_params.get("virtio_port_name_prefix")
            serial_name = serial_params.get("serial_name")
            if not serial_name:
                serial_name = prefix if prefix else serial_id
                serial_props["name"] = serial_name
            serial["props"] = serial_props
            serial["backend"] = serial_backend
            serials.append(serial)
        return serials

    def _define_spec_rngs(self):
        """
        Define the specification of RNG devices

        :return: The specification of RNG devices.
                 Schema format: [
                    {
                    "id": str,
                    "type": str,
                    "bus": str,
                    "props": dict,
                    "backend": {
                                "id": str,
                                "type": str,
                                "props": dict,
                            }
                    },
                 ]
        :rtype: list
        """
        rngs = []

        for virtio_rng in self._params.objects("virtio_rngs"):
            rng = dict()
            rng_props = dict()
            rng_backend = dict()
            rng_backend_props = dict()

            rng_params = self._params.object_params(virtio_rng)
            dev_id = utils_misc.generate_random_string(8)
            rng["id"] = f"virtio-rng-{dev_id}"
            rng["bus"] = self._get_pci_bus(rng_params, "vio_rng", True)
            rng["type"] = "pci"
            machine_type = self.params.get("machine_type", "pc")
            if "s390" in machine_type:
                rng["type"] = "ccw"

            for pro, val in six.iteritems(rng_params):
                suffix = "_%s" % "virtio-rng"
                if pro.endswith(suffix):
                    idx = len(suffix)
                    rng_props[pro[:-idx]] = val

            rng["props"] = rng_props

            if rng_params.get("backend"):
                if rng_params.get("backend") == "rng-builtin":
                    backend_type = "builtin"
                elif rng_params.get("backend") == "rng-random":
                    backend_type = "random"
                elif rng_params.get("backend") == "rng-egd":
                    backend_type = "egd"
                else:
                    raise NotImplementedError

                rng_backend["type"] = backend_type

            for pro, val in six.iteritems(rng_params):
                suffix = "_%s" % rng_params["backend_type"]
                if pro.endswith(suffix):
                    idx = len(suffix)
                    rng_backend_props[pro[:-idx]] = val

            dev_id = utils_misc.generate_random_string(8)
            rng_backend["id"] = "%s-%s" % (rng_params["backend_type"], dev_id)

            rng_backend_chardev = dict()
            if rng_params["backend_type"] == "chardev":
                rng_backend_chardev["type"] = rng_params["rng_chardev_backend"]

                for pro, val in six.iteritems(rng_params):
                    suffix = "_%s" % rng_params["%s_type" % rng_backend_chardev["type"]]
                    if pro.endswith(suffix):
                        idx = len(suffix)
                        rng_backend_chardev["props"][pro[:-idx]] = val

                dev_id = utils_misc.generate_random_string(8)
                dev_id = "%s-%s" % (
                    rng_params["%s_type" % rng_backend_chardev["type"]],
                    dev_id,
                )
                rng_backend_chardev["id"] = dev_id
            if rng_backend_chardev:
                rng_backend["props"]["chardev"] = rng_backend_chardev

            rng_backend["props"] = rng_backend_props
            rng["backend"] = rng_backend
            rngs.append(rng)

        return rngs

    def _define_spec_debugs(self):
        """
        Define the specification of debug devices

        :return: The specification of debug devices.
                 Schema format: [
                    {
                    "type": str,
                    "bus": str,
                    "props": dict,
                    "backend": {
                                "type": str,
                                "props": dict,
                            },
                    },
                 ]
        :rtype: list
        """
        debugs = []
        debug = dict()
        debug_props = dict()
        debug_backend = dict()

        if self._params.get("enable_debugcon") == "yes":
            debug["type"] = "isa-debugcon"

        if self._params.get("anaconda_log", "no") == "yes":
            debug["type"] = "anaconda_log"
            debug["bus"] = self._get_pci_bus(self.params, None, True)

        debug_props["backend"] = debug_backend
        debug["props"] = debug_props
        debugs.append(debug)
        return debugs

    def _define_spec_controllers(self):
        """
        Define the specification of controller devices

        :return: The specification of controller devices.
                 Schema format: [
                    {
                    "id": str,
                    "type": str,
                    "bus": str,
                    "props": dict
                    },
                 ]
        :rtype: list
        """
        controllers = []
        controller = dict()
        controller_props = dict()

        # Add USB controllers
        usbs = self._params.objects("usbs")
        if usbs:
            for usb_name in usbs:
                usb_params = self._params.object_params(usb_name)
                controller["id"] = usb_name
                controller["type"] = usb_params.get("usb_type")
                controller["bus"] = self._get_pci_bus(usb_params, "usbc", True)
                controller_props["multifunction"] = usb_params.get("multifunction")
                controller_props["masterbus"] = usb_params.get("masterbus")
                controller_props["firstport"] = usb_params.get("firstport")
                controller_props["freq"] = usb_params.get("freq")
                controller_props["max_ports"] = int(usb_params.get("max_ports", 6))
                controller_props["addr"] = usb_params.get("pci_addr")
                controller["props"] = controller_props
                controllers.append(controller)

        return controllers

    def _define_spec_usbs(self):
        """
        Define the specification of USB devices

        :return: The specification of controller devices.
                 Schema format: [
                    {
                    "id": str,
                    "type": str,
                    "bus": str,
                    "props": dict
                    },
                 ]
        :rtype: list
        """
        usbs = []

        for usb in self._params.objects("usb_devices"):
            usb_params = self._params.object_params(usb)
            usb = dict()
            usb_props = dict()
            usb["id"] = f"usb-{usb}"
            usb["type"] = usb_params.get("usbdev_type")
            usb["bus"] = usb_params.get("pci_bus", "pci.0")
            usb_props["name"] = usb

            if usb["type"] == "usb-host":
                usb_props["hostbus"] = usb_params.get("usbdev_option_hostbus")
                usb_props["hostaddr"] = usb_params.get("usbdev_option_hostaddr")
                usb_props["hostport"] = usb_params.get("usbdev_option_hostport")
                vendorid = usb_params.get("usbdev_option_vendorid")
                if vendorid:
                    usb_props["vendorid"] = "0x%s" % vendorid
                productid = usb_params.get("usbdev_option_productid")
                if productid:
                    usb_props["productid"] = "0x%s" % productid

            usb_props["controller"] = usb_params.get("usb_controller")
            usb_props["bus"] = usb_params.get("usbdev_bus")
            usb_props["port"] = usb_params.get("usbdev_port")
            usb_props["serial"] = usb_params.get("usbdev_serial")
            usb["props"] = usb_props
            usbs.append(usb)

    def _define_spec_iothreads(self):
        """
        Define the specification of iothreads

        :return: The specification of iothreads.
                 Schema format: [
                    {
                    "id": str,
                    "props": dict
                    },
                 ]
        :rtype: list
        """
        iothreads = []
        iothread = dict()
        iothread_props = dict()

        iothreads_lst = self._params.objects("iothreads")

        for _iothread in iothreads_lst:
            iothread["id"] = _iothread
            iothread_params = self._params.object_params(iothread)

            for key, val in {"iothread_poll_max_ns": "poll-max-ns"}.items():
                if key in iothread_params:
                    iothread_props[val] = iothread_params.get(key)

            iothread["props"] = iothread_props
            iothreads.append(iothread)

        return iothreads

    def _define_spec_throttle_groups(self):
        """
        Define the specification of throttle groups

        :return: The specification of throttle groups.
                 Schema format: [
                    {
                    "id": str,
                    "props": dict
                    },
                 ]
        :rtype: list
        """
        iothreads = []
        iothread = dict()
        iothread_props = dict()

        for group in self._params.objects("throttle_groups"):
            group_params = self._params.object_params(group)
            iothread["id"] = group
            throttle_group_parameters = group_params.get(
                "throttle_group_parameters", "{}"
            )
            iothread_props.update(json.loads(throttle_group_parameters))
            iothread["props"] = iothread_props

            iothreads.append(iothread)

        return iothreads

    def _define_spec_disks(self):
        """
        Define the specification of the disks

        :return: The specification of the disks.
                 Schema format: [
                    {
                    "id": str,
                    "type": str,
                    "source": {
                                "id": str, #volume id
                            },
                    "driver": {
                                "id": str,
                                "type": str,
                                "props": dict
                            },
                    "device": {
                                "id": str,
                                "bus": str,
                                "props": dict
                                },
                    },
                 ]
        :rtype: list
        """
        disks = []
        disk = dict()
        disk_props = dict()

        source = dict()
        source_props = dict()

        driver = dict()
        driver_props = dict()

        device = dict()
        device_props = dict()

        for image_name in self._params.objects("images"):
            disk["id"] = image_name
            disk["type"] = "disk"
            image_params = self._params.object_params(image_name)

            # vt_images = self._env.get_vm_images(self._name)
            # for image in vt_images:
            #     if image.tag == image_name:
            #         source["id"] = image.uuid
            #         image_info = vt_image.api.get_info(image.uuid)
            #         volume_id = image_info.get("volume_id")
            #         source["id"] = "volume1"
            # disk["source"] = "volume_%s" % image_name
            try:
                image_id = vt_imgr.get_image_by_tag(image_name)
                disk["source"] = vt_imgr.query_image(image_id)
            except:
                LOG.error("----->Could not find image  %s and hard code for it",
                         image_name)
                disk["source"] = "volume_%s" % image_name

            LOG.debug("disk source: %s", disk["source"])

            if self._params.get("index_enable") == "yes":
                drive_index = image_params.get("drive_index")
                driver_props["index"] = drive_index
            image_bootindex = image_params.get("bootindex")
            device_props["bootindex"] = image_bootindex

            drive_format = image_params.get("drive_format", "")
            if drive_format == "virtio":  # translate virtio to ccw/device
                machine_type = image_params.get("machine_type")
                if "s390" in machine_type:  # s390
                    drive_format = "virtio-blk-ccw"
                elif "mmio" in machine_type:  # mmio-based machine
                    drive_format = "virtio-blk-device"

            driver_props["cache"] = image_params.get("drive_cache")
            driver_props["werror"] = image_params.get("drive_werror")
            driver_props["rerror"] = image_params.get("drive_rerror")
            driver_props["serial"] = image_params.get("drive_serial")
            driver_props["readonly"] = image_params.get("image_readonly")
            driver_props["aio"] = image_params.get("image_aio")

            drv_extra_params = image_params.get("drv_extra_params")
            if drv_extra_params:
                drv_extra_params = (
                    _.split("=", 1) for _ in drv_extra_params.split(",") if _
                )
                for key, value in drv_extra_params:
                    driver_props[key] = value

            driver["props"] = driver_props
            driver["type"] = drive_format

            disk["driver"] = driver

            device["id"] = image_name
            device["bus"] = self._get_pci_bus(image_params, "disk", True)
            device_props["logical_block_size"] = image_params.get("logical_block_size")
            device_props["physical_block_size"] = image_params.get(
                "physical_block_size"
            )
            device_props["min_io_size"] = image_params.get("min_io_size")
            device_props["opt_io_size"] = image_params.get("opt_io_size")

            blk_extra_params = image_params.get("blk_extra_params")
            if blk_extra_params:
                blk_extra_params = (
                    _.split("=", 1) for _ in blk_extra_params.split(",") if _
                )
                for key, value in blk_extra_params:
                    device_props[key] = value

            device["props"] = device_props
            disk["device"] = device

            disks.append(disk)

        # for cdrom in self._params.objects("cdroms"):
        #     image_params = self._params.object_params(cdrom)
        #     disk["id"] = cdrom
        #     disk["type"] = "cdrom"
        #     disks.append(disk)
        #
        # for floppy_name in self._params.objects("floppies"):
        #     image_params = self._params.object_params(floppy_name)
        #     disk["id"] = floppy_name
        #     disk["type"] = "floopy"
        #     disks.append(disk)

        return disks

    def _define_spec_filesystems(self):
        """
        Define the specification of the filesystems

        :return: The specification of the filesystems.
                 Schema format: [
                    {
                    "id": str,
                    "type": str,
                    "bus":str,
                    "driver": {
                            "type": str,
                            "props": dict
                            },
                    "target": str,
                    "source": {
                            "type": str,
                            "props": dict
                        },
                    },
                 ]
        :rtype: list
        """
        filesystems = []
        filesystem = dict()
        fs_driver = dict()
        fs_driver_props = dict()
        fs_source = dict()
        fs_source_props = dict()

        for fs in self._params.objects("filesystems"):
            filesystem["id"] = fs
            filesystem_params = self._params.object_params(fs)
            filesystem["target"] = filesystem_params.get("fs_target")
            fs_source["type"] = filesystem_params.get("fs_source_type", "mount")

            if fs_source["type"] == "mount":
                fs_source_props["path"] = filesystem_params.get("fs_source_dir")

            fs_driver["type"] = filesystem_params.get("fs_driver")
            if fs_driver["type"] == "virtio-fs":
                fs_driver_props["binary"] = filesystem_params.get(
                    "fs_binary", "/usr/libexec/virtiofsd"
                )
                extra_options = filesystem_params.get("fs_binary_extra_options")
                fs_driver_props["options"] = extra_options
                enable_debug_mode = filesystem_params.get("fs_enable_debug_mode", "no")
                fs_driver_props["debug_mode"] = enable_debug_mode

            fs_driver_props.update(
                json.loads(filesystem_params.get("fs_driver_props", "{}"))
            )

            fs_source["props"] = fs_source_props
            filesystem["source"] = fs_source
            fs_driver["props"] = fs_driver_props
            filesystem["driver"] = fs_driver

            filesystems.append(filesystem)

        return filesystems

    def _define_spec_nets(self):
        """
        Define the specification of the network

        :return: The specification of the network.
                 Schema format: [
                 ]
        :rtype: list
        """
        nets = []

        return nets

    def _define_spec_vsocks(self):
        """
        Define the specification of the network

        :return: The specification of the network.
                 Schema format: [
                    {
                    "id": str,
                    "cid": int,
                    "bus": str,
                    },
                 ]
        :rtype: list
        """
        vsocks = []
        vsock = dict()
        _vsocks = self._params.objects("vsocks")
        if _vsocks:
            min_cid = 3
            for _vsock in _vsocks:
                vsock["id"] = _vsock
                vsock["bus"] = self._params.get("pci_bus")
                vsock["cid"] = min_cid
                min_cid = min_cid + 1
                vsocks.append(vsock)

        return vsocks

    def _define_spec_os(self):
        """
        Define the specification of the OS

        :return: The specification of the OS.
                 Schema format: {
                            "arch": str,
                            "kernel": str,
                            "initrd": str,
                            "cmdline": str,
                            "boot": {
                                "menu": str,
                                "order": str,
                                "once": str,
                                "strict": str,
                                "reboot_time": str,
                                "splash_time"": str,
                            }
                            "bios": str,
                            }
        :rtype: dict
        """
        os = dict()

        os["arch"] = self._params.get("vm_arch_name", "auto")
        os["kernel"] = self._params.get("kernel")
        os["initrd"] = self._params.get("initrd")
        os["cmdline"] = self._params.get("kernel_params")

        os["boot"] = dict()
        os["boot"]["menu"] = self._params.get("boot_menu")
        os["boot"]["order"] = self._params.get("boot_order")
        os["boot"]["once"] = self._params.get("boot_once")
        os["boot"]["strict"] = self._params.get("boot_strict")
        os["boot"]["reboot_time"] = self._params.get("boot_reboot_timeout")
        os["boot"]["splash_time"] = self._params.get("boot_splash_time")

        os["bios"] = self._params.get("bios_path")

        return os

    def _define_spec_graphics(self):
        """
        Define the specification of the graphics

        :return: The specification of the graphics.
                 Schema format: [
                                    {
                                    "type": str,
                                    "props": dict,
                                    },
                            ]
        :rtype: list
        """
        graphics = []
        graphic = dict()
        graphic_props = dict()
        graphic_type = self._params.get("display")

        if graphic_type == "vnc":
            graphic_props["password"] = self._params.get("vnc_password", "no")
            vnc_extra_params = self._params.get("vnc_extra_params")
            if vnc_extra_params:
                for kay, val in vnc_extra_params.strip(",").split(",").split("=", 1):
                    graphic_props[kay] = val

        graphic["type"] = graphic_type
        graphic["props"] = graphic_props
        graphics.append(graphic)

        return graphics

    def _define_spec_rtc(self):
        """
        Define the specification of the rtc

        :return: The specification of the rtc.
                 Schema format: {base: str, clock: str, driftfix: str}
        :rtype: str
        """
        rtc = dict()
        rtc["base"] = self._params.get("rtc_base")
        rtc["clock"] = self._params.get("rtc_clock")
        rtc["driftfix"] = self._params.get("rtc_drift")
        return rtc

    def _define_spec_tpms(self):
        """
        Define the specification of the TPMs

        :return: The specification of the TPMs.
                 Schema format: [
                                    {
                                    "id": str,
                                    "type": str,
                                    "props": dict,
                                    "model": {
                                                "type": str,
                                                "props": dict,
                                            }
                                    },
                            ]
        :rtype: list
        """
        tpms = []

        for _tpm in self._params.objects("tpms"):
            tpm_params = self._params.object_params(_tpm)
            tpm = dict()
            tpm["id"] = _tpm
            tpm_props = dict()
            tpm_model = dict()
            tpm_model_type = tpm_params.get("tpm_model")
            tpm_model_props = dict()
            tpm["type"] = tpm_params.get("tpm_type")
            tpm_props["version"] = tpm_params.get("tpm_version")

            if (
                tpm["type"] == "emulator"
            ):  # how to define the bin parameter with different nodes?
                tpm_props["bin"] = tpm_params.get("tpm_bin", "/usr/bin/swtpm")
                tpm_props["setup_bin"] = tpm_params.get(
                    "tpm_setup_bin", "/usr/bin/swtpm_setup"
                )
                tpm_props["bin_extra_options"] = tpm_params.get("tpm_bin_extra_options")
                tpm_props["setup_bin_extra_options"] = tpm_params.get(
                    "tpm_setup_bin_extra_options"
                )

            elif tpm["type"] == "passthrough":
                tpm_props["path"] = self._params.get("tpm_device_path")

            tpm["props"] = tpm_props
            tpm_model_props.update(json.loads(tpm_params.get("tpm_model_props", "{}")))
            tpm_model["type"] = tpm_model_type
            tpm_model["props"] = tpm_model_props

            tpm["model"] = tpm_model

            tpms.append(tpm)

        return tpms

    def _define_spec_power_management(self):
        """
        Define the specification of the Power management

        :return: The specification of the Power management.
                 Schema format: {
                                    "no_shutdown": bool
                                }
        :rtype: dict
        """
        pm = dict()

        pm["no_shutdown"] = self._params.get("no_shutdown") == "yes"

        return pm

    def _define_spec_inputs(self):
        """
        Define the specification of the inputs

        :return: The specification of the inputs.
                 Schema format: [
                                    {
                                    "id": str,
                                    "type": str,
                                    "bus": str,
                                    "props": dict,
                                    },
                            ]
        :rtype: list
        """
        inputs = []

        for input_device in self._params.objects("inputs"):
            input_params = self._params.object_params(input_device)
            input = dict()
            input["id"] = input_device

            dev_map = {
                "mouse": {"virtio": "virtio-mouse"},
                "keyboard": {"virtio": "virtio-keyboard"},
                "tablet": {"virtio": "virtio-tablet"},
            }
            input_type = dev_map.get(input_params["input_dev_type"])
            bus_type = input_params["input_dev_bus_type"]

            machine_type = input_params.get("machine_type", "")
            bus = "PCI"
            if machine_type.startswith("q35") or machine_type.startswith("arm64"):
                bus = "PCIE"

            if bus_type == "virtio":
                if "-mmio:" in machine_type:
                    bus = "virtio-bus"
                elif machine_type.startswith("s390"):
                    bus = "virtio-bus"

            input["type"] = input_type
            input["bus"] = bus
            inputs.append(input)

        return inputs

    def _define_spec_balloons(self):
        """
        Define the specification of the balloons

        :return: The specification of the balloons.
                 Schema format: [
                                    {
                                    "id": str,
                                    "type": str,
                                    "bus": str,
                                    "props": dict,
                                    },
                            ]
        :rtype: list
        """
        balloons = []

        for balloon_device in self._params.objects("balloon"):
            balloon_params = self._params.object_params(balloon_device)
            balloon = dict()
            balloon["id"] = balloon_device
            balloon["type"] = balloon_params["balloon_dev_devid"]
            balloon_props = dict()

            balloon_props["old_format"] = (
                balloon_params.get("balloon_use_old_format", "no") == "yes"
            )
            balloon_props["deflate_on_oom"] = balloon_params.get(
                "balloon_opt_deflate_on_oom"
            )
            balloon_props["guest_stats_polling_interval"] = balloon_params.get(
                "balloon_opt_guest_polling"
            )
            balloon_props["free_page_reporting"] = balloon_params.get(
                "balloon_opt_free_page_reporting"
            )

            if balloon_params.get("balloon_dev_add_bus") == "yes":
                balloon["bus"] = self._get_pci_bus(balloon_params, "balloon", True)

            balloon["props"] = balloon_props
            balloons.append(balloon)

        return balloons

    def _define_spec_keyboard_layout(self):
        """
        Define the specification of the keyboard layout

        :return: The specification of the keyboard layout.
                 Schema format: string
        :rtype: string
        """
        optsinfo = self._params.get("keyboard_layout")
        options = []
        if optsinfo:
            for info in optsinfo:
                key, val = info[:2]
                if key and val:
                    options.append("%s=%%(%s)s" % (key, key))
                else:
                    options += list(filter(None, info[:2]))
            options = ",".join(options)
            return f"-k {options}"

    def _parse_params(self):
        spec = dict()
        spec["name"] = self._define_spec_name()
        spec["uuid"] = self._define_spec_uuid()
        spec["preconfig"] = self._define_spec_preconfig()
        spec["sandbox"] = self._define_spec_sandbox()
        spec["defaults"] = self._define_spec_defaults()
        spec["machine"] = self._define_spec_machine()
        spec["launch_security"] = self._define_spec_launch_security()
        spec["iommu"] = self._define_spec_iommu()
        spec["vga"] = self._define_spec_vga()
        spec["watchdog"] = self._define_spec_watchdog()
        spec["pci_controllers"] = self._define_spec_pci_controllers()
        spec["memory"] = self._define_spec_memory()
        spec["cpu"] = self._define_spec_cpu()
        spec["numa"] = self._define_spec_numa()
        spec["soundcards"] = self._define_spec_soundcards()
        spec["monitors"] = self._define_spec_monitors()
        spec["panics"] = self._define_spec_panics()
        spec["vmcoreinfo"] = self._define_spec_vmcoreinfo()
        spec["serials"] = self._define_spec_serials()
        spec["rngs"] = self._define_spec_rngs()
        spec["debugs"] = self._define_spec_debugs()
        spec["controllers"] = self._define_spec_controllers()
        spec["usbs"] = self._define_spec_usbs()
        spec["iothreads"] = self._define_spec_iothreads()
        spec["throttle_groups"] = self._define_spec_throttle_groups()
        spec["disks"] = self._define_spec_disks()
        spec["filesystems"] = self._define_spec_filesystems()
        spec["nets"] = self._define_spec_nets()
        spec["vsocks"] = self._define_spec_vsocks()
        spec["os"] = self._define_spec_os()
        spec["graphics"] = self._define_spec_graphics()
        spec["rtc"] = self._define_spec_rtc()
        # Let's comment out the spec for migration
        # [qemu output] qemu-kvm: tpm-emulator: Setting the stateblob (type 1) failed with a TPM error 0x1f
        # [qemu output] qemu-kvm: error while loading state for instance 0x0 of device 'tpm-emulator'
        # spec["tpms"] = self._define_spec_tpms()
        spec["power_management"] = self._define_spec_power_management()
        spec["inputs"] = self._define_spec_inputs()
        spec["balloons"] = self._define_spec_balloons()
        spec["keyboard_layout"] = self._define_spec_keyboard_layout()
        # LOG.debug("Spec:", json.dumps(spec, indent=4, separators=(",", ": ")))
        return spec
