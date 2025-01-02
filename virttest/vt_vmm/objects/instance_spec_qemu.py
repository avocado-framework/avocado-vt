import json
import logging
import uuid
import six
import re
import os

from functools import reduce
from operator import mul

from virttest import utils_misc
from virttest import qemu_storage
from virttest.qemu_capabilities import Flags
from virttest.utils_version import VersionInterval
from virttest.qemu_devices import qdevices
from virttest.utils_params import Params

from avocado.utils import process

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..objects import instance_spec
from .instance_exception import InstanceSpecError

LOG = logging.getLogger("avocado." + __name__)


# FIXME: To keep the consistency for the previous version
class CpuInfo(object):

    """
    A class for VM's cpu information.
    """

    def __init__(
        self,
        model=None,
        vendor=None,
        flags=None,
        family=None,
        qemu_type=None,
        smp=0,
        maxcpus=0,
        cores=0,
        threads=0,
        dies=0,
        clusters=0,
        sockets=0,
        drawers=0,
        books=0,
    ):
        """
        :param model: CPU Model of VM (use 'qemu -cpu ?' for list)
        :param vendor: CPU Vendor of VM
        :param flags: CPU Flags of VM
        :param family: CPU Family of VM
        :param qemu_type: cpu driver type of qemu
        :param smp: set the number of CPUs to 'n' [default=1]
        :param maxcpus: maximum number of total cpus, including
                        offline CPUs for hotplug, etc
        :param cores: number of CPU cores on one socket (for PC, it's on one die)
        :param threads: number of threads on one CPU core
        :param dies: number of CPU dies on one socket (for PC only)
        :param clusters: number of CPU clusters on one socket (for ARM only)
        :param sockets: number of discrete sockets in the system
        :param drawers: number of discrete drawers in the system (for s390x only)
        :param books: number of discrete books in the system (for s390x only)
        """
        self.model = model
        self.vendor = vendor
        self.flags = flags
        self.family = family
        self.qemu_type = qemu_type
        self.smp = smp
        self.maxcpus = maxcpus
        self.cores = cores
        self.threads = threads
        self.dies = dies
        self.clusters = clusters
        self.sockets = sockets
        self.drawers = drawers
        self.books = books


class QemuSpec(instance_spec.Spec):

    cache_map = {
        "writeback": {
            "write-cache": "on",
            "cache.direct": "off",
            "cache.no-flush": "off",
        },
        "none": {"write-cache": "on", "cache.direct": "on", "cache.no-flush": "off"},
        "writethrough": {
            "write-cache": "off",
            "cache.direct": "off",
            "cache.no-flush": "off",
        },
        "directsync": {
            "write-cache": "off",
            "cache.direct": "on",
            "cache.no-flush": "off",
        },
        "unsafe": {"write-cache": "on", "cache.direct": "off", "cache.no-flush": "on"},
    }

    BLOCKDEV_VERSION_SCOPE = "[2.12.0, )"
    SMP_DIES_VERSION_SCOPE = "[4.1.0, )"
    SMP_CLUSTERS_VERSION_SCOPE = "[7.0.0, )"
    SMP_BOOKS_VERSION_SCOPE = "[8.2.0, )"
    SMP_DRAWERS_VERSION_SCOPE = "[8.2.0, )"
    FLOPPY_DEVICE_VERSION_SCOPE = "[5.1.0, )"
    BLOCKJOB_BACKING_MASK_PROTOCOL_VERSION_SCOPE = "[9.0.0, )"

    def __init__(self, name, vt_params, node):
        super(QemuSpec, self).__init__(name, "qemu", vt_params, node)
        self._qemu_binary = self._params.get("qemu_binary", "qemu")
        self._qemu_machines_info = self._node.proxy.virt.tools.qemu.get_machines_info(self._qemu_binary)
        self._qemu_ver = self._node.proxy.virt.tools.qemu.get_version(self._qemu_binary)[0]
        self._qemu_help = self._node.proxy.virt.tools.qemu.get_help_info(None, self._qemu_binary)
        LOG.debug("Qemu help info: %s", self._qemu_help)
        self._qemu_caps = set()
        self._cpuinfo = CpuInfo()
        self._probe_capabilities()
        self._index_in_use = {}

        self._last_driver_index = 0
        # init the dict index_in_use
        for key in list(self._params.keys()):
            if "drive_index" in key:
                self._index_in_use[self._params.get(key)] = True

    def _none_or_int(self, value):
        """ Helper function which returns None or int() """
        if isinstance(value, int):
            return value
        elif not value:  # "", None, False
            return None
        elif isinstance(value, six.string_types) and value.isdigit():
            return int(value)
        else:
            raise TypeError("This parameter has to be int or none")

    def _probe_capabilities(self):
        """Probe capabilities."""
        # -blockdev
        if self._has_option("blockdev") and self._qemu_ver in VersionInterval(
            self.BLOCKDEV_VERSION_SCOPE
        ):
            self._qemu_caps.add(Flags.BLOCKDEV)
        # -smp dies=?
        if self._qemu_ver in VersionInterval(self.SMP_DIES_VERSION_SCOPE):
            self._qemu_caps.add(Flags.SMP_DIES)
        # -smp clusters=?
        if self._qemu_ver in VersionInterval(self.SMP_CLUSTERS_VERSION_SCOPE):
            self._qemu_caps.add(Flags.SMP_CLUSTERS)
        # -smp drawers=?
        if self._qemu_ver in VersionInterval(self.SMP_DRAWERS_VERSION_SCOPE):
            self._qemu_caps.add(Flags.SMP_DRAWERS)
        # -smp book=?
        if self._qemu_ver in VersionInterval(self.SMP_BOOKS_VERSION_SCOPE):
            self._qemu_caps.add(Flags.SMP_BOOKS)
        # -incoming defer
        if self._has_option("incoming defer"):
            self._qemu_caps.add(Flags.INCOMING_DEFER)
        # -machine memory-backend
        machine_help = self._node.proxy.virt.tools.qemu.get_help_info(
            "-machine none,", self._qemu_binary)
        if re.search(r"memory-backend=", machine_help, re.MULTILINE):
            self._qemu_caps.add(Flags.MACHINE_MEMORY_BACKEND)
        # -object sev-guest
        if self._has_object("sev-guest"):
            self._qemu_caps.add(Flags.SEV_GUEST)
        # -object tdx-guest
        if self._has_object("tdx-guest"):
            self._qemu_caps.add(Flags.TDX_GUEST)
        # -device floppy,drive=$drive
        if self._qemu_ver in VersionInterval(self.FLOPPY_DEVICE_VERSION_SCOPE):
            self._qemu_caps.add(Flags.FLOPPY_DEVICE)
        if self._qemu_ver in VersionInterval(
            self.BLOCKJOB_BACKING_MASK_PROTOCOL_VERSION_SCOPE
        ):
            self._qemu_caps.add(Flags.BLOCKJOB_BACKING_MASK_PROTOCOL)

    def _has_option(self, name):
        return self._node.proxy.virt.tools.qemu.has_option(name, self._qemu_binary)

    def _has_device(self, device):
        """
        :param device: Desired device
        :return: Is the desired device supported by current qemu?
        """
        return self._node.proxy.virt.tools.qemu.has_device(device, self._qemu_binary)

    def _has_object(self, obj):
        """
        :param obj: Desired object string, e.g. 'sev-guest'
        :return: True if the object is supported by qemu, or False
        """
        return self._node.proxy.virt.tools.qemu.has_object(obj, self._qemu_binary)

    def _is_pci_device(self, device):
        return self._node.proxy.virt.tools.qemu.is_pci_device(device, self._qemu_binary)

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

    def _get_pci_bus(self, params, dtype=None, pcie=False):
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
            # for legacy pic device(eg. rtl8139, e1000)
            if self._has_device("pcie-pci-bridge"):
                bridge_type = "pcie-pci-bridge"
            else:
                bridge_type = "pci-bridge"
            return "%s-0" % bridge_type
        return params.get("pci_bus", "pci.0")

    def _get_index(self, index):
        while self._index_in_use.get(str(index)):
            index += 1
        return index

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
        if not self._has_option("sandbox"):
            return sandbox
        sandbox["action"] = action

        props = {}
        if action == "on":
            props = {
                    "elevateprivileges": self._params.get(
                        "qemu_sandbox_elevateprivileges", "deny"
                    ),
                    "obsolete": self._params.get("qemu_sandbox_obsolete", "deny"),
                    "resourcecontrol": self._params.get(
                        "qemu_sandbox_resourcecontrol", "deny"
                    ),
                    "spawn": self._params.get("qemu_sandbox_spawn", "deny"),
                }
        elif action == "off":
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
        """
        defaults = self._params.get("defaults", "no")
        if self._has_option("nodefaults") and defaults != "yes":
            return False
        return True

    def _define_spec_firmware(self, machine_spec):
        """
        Define the specification of the firmware

        :return: The specification of the firmware.
                 Schema format: {
                                    "type": str,
                                    "code": {
                                                path: str,
                                                format: str,
                                                read_only: bool,
                                            },
                                    "vars": {
                                                path: str,
                                                format: str,
                                                read_only: bool,
                                            },
                                }
        :rtype: list
        """
        def is_remote_image(image_filename):
            keywords = ("gluster iscsi rbd nbd "
                        "nvme http https ftp ftps").split()
            for keyword in keywords:
                if image_filename.startswith(keyword):
                    return True
            return False

        firmware = {}
        firmware_code = {}
        firmware_vars = {}
        machine_type = machine_spec.get("type")
        if(("q35" in machine_type and self._params.get("vm_secure_guest_type") != "tdx")
            or machine_type == "pc"):
            firmware_type = "ovmf"
        elif machine_type.split(":")[0] in ("arm64-pci", "arm64-mmio"):
            firmware_type = "avvmf"
        else:
            firmware_type = "unknown"
        images = self._params.objects("images")
        firmware_path = self._params.get(firmware_type + "_path")
        if firmware_path and images:
            image_id = vt_imgr.query_image(images[0], self._name)
            img_format = vt_imgr.get_image_info(
                image_id, f"spec.virt-images.{images[0]}.spec.format").get("format")
            img_filename = vt_imgr.get_image_info(
                image_id, f"spec.virt-images.{images[0]}.spec.volume.spec.uri").get("uri")
            # For OVMF with SEV-ES support and OVMF with TDX support,
            # the vm can be booted without vars file.
            # Add a workaround, skip the processing of pflash vars
            # file here when ovmf_vars_files =.
            pflash_vars_filename = self._params.get(firmware_type + "_vars_filename")
            vars_info = self._node.proxy.virt.firmware.get_vars_info(
                firmware_path, pflash_vars_filename)
            pflash_vars_format = vars_info.get("format")
            if pflash_vars_filename:
                # To ignore the influence from backends
                if is_remote_image(img_filename):  # FIXME:
                    pflash_vars_name = (
                        f"{self._name}_"
                        f"{self._params['guest_name']}_"
                        f"{self._params['image_backend']}_"
                        f"{img_format}_"
                        f"VARS.{pflash_vars_format}"
                    )
                else:
                    img_path, img_name = os.path.split(img_filename)

                    pflash_vars_name = (
                        f"{self._name}_"
                        f"{'_'.join(img_name.split('.'))}_"
                        f"{self._params['image_backend']}_"
                        f"VARS.{pflash_vars_format}"
                    )
                    # pflash_vars_path = os.path.join(img_path, pflash_vars_name)
                    # if not os.access(pflash_vars_path, os.W_OK):
                    #     pflash_vars_path = os.path.join(
                    #         current_data_dir, pflash_vars_name
                    #     )
                    # TODO: support the handling the backing files later
                    # When image has backing files,
                    # treat it as a temporary image
                    # if "backing-filename" in img_info:
                    #     self.temporary_image_snapshots.add(pflash_vars_path)

            pflash0, pflash1 = (firmware_type + "_code", firmware_type + "_vars")

            # Firmware code file
            if Flags.BLOCKDEV in self._qemu_caps:
                pflash_code_filename = self._params[firmware_type + "_code_filename"]
                code_info = self._node.proxy.virt.firmware.get_code_info(
                    firmware_path, pflash_code_filename)
                firmware_code["path"] = code_info.get("path")
                firmware_code["format"] = code_info.get("format")
                firmware_code["read_only"] = True
            # TODO: support the drive model
            # else:
            #     devs.append(qdevices.QDrive(pflash0, use_device=False))
            #     devs[-1].set_param("if", "pflash")
            #     devs[-1].set_param("format", pflash_code_format)
            #     devs[-1].set_param("readonly", "on")
            #     devs[-1].set_param("file", pflash_code_path)

            # Firmware vars file
            if pflash_vars_filename:
                pflash_vars_src_path = os.path.join(firmware_path, pflash_vars_filename)
                firmware_vars["restore"] = False
                if (
                        not self._node.proxy.virt.firmware.is_vars_path_valid(pflash_vars_name)
                        or self._params.get("restore_%s_vars" % firmware_type) == "yes"
                ):
                    firmware_vars["restore"] = True

                if Flags.BLOCKDEV in self._qemu_caps:
                    firmware_vars["src_path"] = pflash_vars_src_path
                    firmware_vars["dst_path"] = pflash_vars_name
                    firmware_vars["format"] = vars_info.get("format")
                    firmware_vars["read_only"] = False

                # TODO: support the drive model
                # else:
                #     devs.append(qdevices.QDrive(pflash1, use_device=False))
                #     devs[-1].set_param("if", "pflash")
                #     devs[-1].set_param("format", pflash_vars_format)
                #     devs[-1].set_param("file", pflash_vars_path)
        firmware["type"] = firmware_type
        firmware["code"] = firmware_code
        firmware["vars"] = firmware_vars
        return firmware

    def _define_spec_machine(self, spec_controllers):
        """
        Define the specification of the machine.

        :return: The specification of the machine.
                 Schema format: {
                                    "type": str,
                                    "props": dict,
                                    # "controllers": [
                                    #                  {
                                    #                      "type": str,
                                    #                      "props": dict,
                                    #                  }
                                    #              ]
                                }
        :rtype: dict
        """
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
        if self._has_device("pcie-root-port"):
            root_port_type = "pcie-root-port"
        else:
            root_port_type = "ioh3420"

        if self._has_device("pcie-pci-bridge"):
            pci_bridge_type = "pcie-pci-bridge"
        else:
            pci_bridge_type = "pci-bridge"
        pcie_root_port_params = self._params.get("pcie_root_port_params")

        if "q35" in machine["type"]:
            # add default pcie root port plugging pcie device
            root_pci_controller = dict()
            root_pci_controller["id"] = "%s-0" % root_port_type
            root_pci_controller["type"] = root_port_type
            root_pci_controller["bus"] = self._params.get("pci_bus", "pci.0")
            root_pci_controller_props = dict()
            # reserve slot 0x0 for plugging in  pci bridge
            root_pci_controller_props["reserved_slots"] = "0x0"
            # FIXME:
            root_pci_controller_props["root_port_props"] = pcie_root_port_params
            if root_pci_controller["type"] == "pcie-root-port":
                root_pci_controller_props["multifunction"] = "on"
            root_pci_controller["props"] = root_pci_controller_props
            spec_controllers.insert(0, root_pci_controller)

            # add pci bridge for plugging in legacy pci device
            pci_bridge_controller = dict()
            pci_bridge_controller_props = dict()
            pci_bridge_controller["id"] = "%s-0" % pci_bridge_type
            pci_bridge_controller["bus"] = root_pci_controller["id"]
            pci_bridge_controller["type"] = pci_bridge_type
            pci_bridge_controller_props["addr"] = "0x0"
            pci_bridge_controller["props"] = pci_bridge_controller_props
            spec_controllers.insert(1, pci_bridge_controller)

        # if (machine["type"] == "pc" or "i440fx" in machine["type"]
        #         or machine["type"].startswith("pseries")
        #         or machine["type"].startswith("s390")):
        #     machine_controllers.append(
        #         {
        #             "type": "cpu",
        #             "props": {"model": self._params.get("cpu_model")}
        #         }
        #     )

        machine["props"] = machine_props

        return machine

    def _define_spec_launch_security(self):
        """
        Define the specification of the launch security

        :return: The specification of the launch security.
                 Schema format: {
                                    "type": str,
                                    "id": str,
                                    "props": dict
                                }
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
                 Schema format: {
                                    "type": str,
                                    "bus": str,
                                    "props": dict
                                }
        :rtype: dict
        """
        iommu = dict()
        iommu_props = dict()

        if self._params.get("intel_iommu") and self._has_device("intel-iommu"):
            iommu["type"] = "intel-iommu"
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

        elif self._params.get("virtio_iommu") and self._has_device(
                "virtio-iommu-pci"):
            iommu["type"] = "virtio-iommu-pci"
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
                 Schema format: {
                                    "type": str,
                                    "bus": str
                                }
        :rtype: dict
        """
        vga = dict()

        if self._params.get("vga"):
            _vga = self._params.get("vga")
            fallback = self._params.get("vga_use_legacy_expression") == "yes"
            machine_type = self._params.get("machine_type", "")
            pcie = machine_type.startswith("q35") or machine_type.startswith(
                "arm64-pci"
            )
            vga["bus"] = self._get_bus(self._params, "vga", pcie)
            vga_dev_map = {
                "std": "VGA",
                "cirrus": "cirrus-vga",
                "vmware": "vmware-svga",
                "qxl": "qxl-vga",
                "virtio": "virtio-vga",
            }
            vga_dev = vga_dev_map.get(_vga, None)
            if machine_type.startswith("arm64-pci:"):
                if _vga == "virtio" and not self._has_device(vga_dev):
                    # Arm doesn't usually supports 'virtio-vga'
                    vga_dev = "virtio-gpu-pci"
            elif machine_type.startswith("s390-ccw-virtio"):
                if _vga == "virtio":
                    vga_dev = "virtio-gpu-ccw"
                else:
                    vga_dev = None
            elif "-mmio:" in machine_type:
                if _vga == "virtio":
                    vga_dev = "virtio-gpu-device"
                else:
                    vga_dev = None
            if vga_dev is None:
                fallback = True
                vga["bus"] = None
            # fallback if qemu not has such a device
            elif not self._has_device(vga_dev):
                fallback = True
            if fallback:
                vga_dev = "VGA-%s" % _vga
            vga["type"] = vga_dev

        return vga

    def _define_spec_watchdog(self):
        """
        Define the specification of the watch dog

        :return: The specification of the watch dog.
                 Schema format: {
                                    "type": str,
                                    "bus": str,
                                    "action": str,
                                }
        :rtype: dict
        """
        watchdog = dict()

        if self._params.get("enable_watchdog", "no") == "yes":
            watchdog["type"] = self._params.get("watchdog_device_type")
            if watchdog["type"] and self._has_device(watchdog["type"]):
                if self._is_pci_device(watchdog["type"]):
                    watchdog["bus"] = self._get_pci_bus(self._params, None, False)
            watchdog["action"] = self._params.get("watchdog_action", "reset")

        return watchdog

    def _define_spec_controllers(self):
        """
        Define the specification of the controllers
        Note: There is controller order here: [pci, usb, scsi, ide, sata, virtio-serial]
        :return: The specification of the controllers.
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

        controllers = []

        # Define the PCI controller
        for pcic in self._params.objects("pci_controllers"):
            pci_controller = dict()
            pcic_params = self._params.object_params(pcic)
            pci_controller["id"] = pcic
            pci_controller["type"] = pcic_params.get("type", "pcie-root-port")
            pci_controller["bus"] = pcic_params.get("pci_bus", "pci.0")
            props = dict()
            props["reserved_slots"] = self._params.get("reserved_slots")
            pci_controller["props"] = props
            controllers.append(pci_controller)

        # Define the extra PCIe controllers
        extra_port_num = int(self._params.get("pcie_extra_root_port", 0))
        for num in range(extra_port_num):
            pci_controller = dict()
            pci_controller["id"] = "pcie_extra_root_port_%d" % num
            pci_controller["type"] = "pcie-root-port"
            pci_controller["bus"] = "pci.0"

            props = dict()
            pcie_root_port_params = self._params.get("pcie_root_port_params")
            if pcie_root_port_params:
                for extra_param in pcie_root_port_params.split(","):
                    key, value = extra_param.split("=")
                    props[key] = value

            func_num = num % 8
            if func_num == 0:
                props["multifunction"] = "on"

            pci_controller["props"] = props
            controllers.append(pci_controller)

        # Define USB controller specification
        usbs = self._params.objects("usbs")
        if usbs:
            for usb_name in usbs:
                usb_controller = dict()
                usb_controller_props = dict()
                usb_params = self._params.object_params(usb_name)
                usb_type = usb_params.get("usb_type")
                if not self._has_device(usb_type):
                    raise InstanceSpecError("Unknown USB: %s" % usb_type)

                usb_controller["id"] = usb_name
                usb_controller["type"] = usb_params.get("usb_type")
                usb_controller["bus"] = self._get_pci_bus(usb_params, "usbc", True)
                usb_controller_props["multifunction"] = usb_params.get("multifunction")
                usb_controller_props["masterbus"] = usb_params.get("masterbus")
                usb_controller_props["firstport"] = usb_params.get("firstport")
                usb_controller_props["freq"] = usb_params.get("freq")
                usb_controller_props["max_ports"] = int(usb_params.get("max_ports", 6))
                usb_controller_props["addr"] = usb_params.get("pci_addr")
                usb_controller["props"] = usb_controller_props
                controllers.append(usb_controller)

        return controllers

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
                        "devices": [
                                        {
                                            "backend": {
                                                        "type": str,
                                                        "id": str,
                                                        "props": dict,
                                                        },
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

        devices = []
        for name in self._params.objects("mem_devs"):
            device = dict()
            backend = dict()

            params = self._params.object_params(name)
            _params = params.object_params("mem")
            backend["type"] = _params.setdefault("backend", "memory-backend-ram")
            backend["id"] = "%s-%s" % ("mem", name)
            attrs = qdevices.Memory.__attributes__[backend["type"]][:]
            backend["props"] = params.copy_from_keys(attrs)
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
                    dev_props = {k: v for k, v in dimm_params.copy_from_keys(attrs).items()}
                    dev_props.update(params.get_dict("dimm_extra_params"))

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
                    dev_props = {k: v for k, v in virtio_mem_params.copy_from_keys(supported).items()}
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

            device["backend"] = backend
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
                                    },
                        "devices": [
                                        {
                                        "id": str,
                                        "type": str,
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

        # Add vcpu devices
        # TODO: support it in the future since did not get the purpose of the following code
        # vcpu_bus = devices.get_buses({"aobject": "vcpu"})
        # if vcpu_bus and params.get("vcpu_devices"):
        #     vcpu_bus = vcpu_bus[0]
        #     vcpu_bus.initialize(self._cpuinfo)
        #     vcpu_devices = params.objects("vcpu_devices")
        #     params["vcpus_count"] = str(vcpu_bus.vcpus_count)

        for vcpu_name in self._params.objects("vcpu_devices"):
            params = self._params.object_params(vcpu_name)
            cpu_device["id"] = params.get("vcpu_id", vcpu_name)
            cpu_driver = params.get("cpu_driver")
            if not self._has_device(cpu_driver):
                raise InstanceSpecError("Unsupport cpu driver %s" % cpu_driver)
            cpu_device["type"] = cpu_driver
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
        for numa_node in self._params.objects("guest_numa_nodes"):
            pass
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
        soundhw = self._params.get("soundcards")
        if soundhw:
            bus = self._get_pci_bus(self._params, "soundcard")
            if not self._has_option("device") or soundhw == "all":
                for sndcard in ("AC97", "ES1370", "intel-hda"):
                    soundcard = dict()
                    # Add all dummy PCI devices and the actual command below
                    soundcard["type"] = "SND-%s" % sndcard
                    soundcard["bus"] = bus
                soundcards.append(soundcard)
            for sound_device in self._params.get("soundcards").split(","):
                soundcard = {}
                if "hda" in sound_device:
                    soundcard["type"] = "intel-hba"
                elif sound_device in ("es1370", "ac97"):
                    soundcard["type"] = sound_device.upper()
                else:
                    soundcard["type"] = sound_device

                soundcard["bus"] = bus
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
                                    "id": str,
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
            monitor["id"] = "qmp_id_%s" % monitor_name
            monitor["type"] = monitor_params.get("monitor_type")

            monitor_props = dict()
            monitor_backend = dict()
            monitor_backend_props = dict()
            # FIXME: hardcoded here
            monitor_filename = "/tmp/monitor-%s-%s" % (monitor_name, self._name)
            # monitor_backend_props["filename"] = monitor_filename

            if monitor["type"] == "qmp":
                if not self._has_option("qmp"):
                    LOG.warning(
                        "Fallback to human monitor since qmp is" " unsupported")
                    monitor["type"] = "hmp"
                elif not self._has_option("chardev"):
                    monitor_props["filename"] = monitor_filename
                else:
                    # Define qmp specification
                    monitor_backend["type"] = monitor_params.get("chardev_backend", "unix_socket")
                    monitor_backend["id"] = "qmp_id_%s" % monitor_name
                    if monitor_backend["type"] == "tcp_socket":
                        host = monitor_params.get("chardev_host", "127.0.0.1")
                        port = str(
                            self._node.proxy.network.find_free_ports(5000, 6000, 1, host)[0])
                        # monitor_backend_props["host"] = host
                        # monitor_backend_props["port"] = port
                        self._params["chardev_host_%s" % monitor_name] = host
                        self._params["chardev_port_%s" % monitor_name] = port
                    elif monitor_backend["type"] == "unix_socket":
                        self._params["monitor_filename_%s" % monitor_name] = monitor_filename
                        # monitor_backend_props["filename"] = monitor_filename
                    else:
                        raise ValueError("Unsupported chardev backend: %s" % monitor_backend["type"])
                    monitor_props["mode"] = "control"

            else:
                if not self._has_option("chardev"):
                    monitor_props["filename"] = monitor_filename
                else:
                    # Define hmp specification
                    monitor_backend["type"] = monitor_params.get("chardev_backend", "unix_socket")
                    monitor_backend["id"] = "hmp_id_%s" % monitor_name
                    if monitor_backend["type"] != "unix_socket":
                        raise NotImplementedError(
                            "human monitor don't support backend" " %s" %  monitor_backend["type"]
                        )
                    self._params["monitor_filename_%s" % monitor_name] = monitor_filename
                    # monitor_backend_props["filename"] = monitor_filename
                    monitor_props["mode"] = "readline"

            # Define the chardev specification
            params = self._params.object_params(monitor_name)
            chardev_id = monitor_backend["id"]
            file_name = self._params["monitor_filename_%s" % monitor_name]
            backend = params.get("chardev_backend", "unix_socket")
            # for tcp_socket and unix_socket, both form to 'socket'
            _backend = "socket" if "socket" in backend else backend
            # Generate -chardev device
            chardev_param = Params({"backend": _backend})
            if backend in [
                "unix_socket",
                "file",
                "pipe",
                "serial",
                "tty",
                "parallel",
                "parport",
            ]:
                chardev_param.update({"path": file_name})
                if backend == "pipe" and params.get("auto_create_pipe",
                                                    "yes") == "yes":
                    # FIXME: skip to support multiple hosts at this moment
                    process.system("mkfifo %s" % file_name)
                if backend == "unix_socket":
                    chardev_param.update(
                        {
                            "abstract": params.get("chardev_abstract"),
                            "tight": params.get("chardev_tight"),
                        }
                    )
            elif backend in ["udp", "tcp_socket"]:
                chardev_param.update(
                    {
                        "host": params["chardev_host"],
                        "port": params["chardev_port"],
                        "ipv4": params.get("chardev_ipv4"),
                        "ipv6": params.get("chardev_ipv6"),
                    }
                )
            if backend == "tcp_socket":
                chardev_param.update({"to": params.get("chardev_to")})
            if "socket" in backend:  # tcp_socket & unix_socket
                chardev_param.update(
                    {
                        "server": params.get("chardev_server", "on"),
                        "wait": params.get("chardev_wait", "off"),
                    }
                )
            elif backend in ["spicevmc", "spiceport"]:
                chardev_param.update(
                    {
                        "debug": params.get("chardev_debug"),
                        "name": params.get("chardev_name"),
                    }
                )
            elif "ringbuf" in backend:
                chardev_param.update(
                    {"ringbuf_write_size": int(
                        params.get("ringbuf_write_size"))}
                )
            monitor_backend_props.update({k: v for k, v in chardev_param.items()})
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
                        "bus": str,
                        "props": dict,
                        },
                    ]
        :rtype: list
        """
        panics = []

        if self._params.get("enable_pvpanic") == "yes":
            panic = dict()
            panic_props = dict()
            panic["id"] = utils_misc.generate_random_id()
            arch = self._node.proxy.platform.get_arch()
            if "aarch64" in self._params.get("vm_arch_name", arch):
                panic["type"] = "pvpanic-pci"
            else:
                panic["type"] = "pvpanic"
            if not self._has_device(panic["type"]):
                LOG.warning("%s device is not supported", panic["type"])
                return []
            if panic["type"] == "pvpanic-pci":
                panic["bus"] = self._get_pci_bus(self._params, None, True)
            else:
                ioport = self._params.get("ioport_pvpanic")
                events = self._params.get("events_pvpanic")
                if ioport:
                    panic_props["ioport"] = ioport
                if events:
                    panic_props["events"] = events
            panic["props"] = panic_props
            panics.append(panic)

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
                                "id": str,
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

        for usb_dev in self._params.objects("usb_devices"):
            usb_params = self._params.object_params(usb_dev)
            usb = dict()
            usb_props = dict()
            usb["type"] = usb_params.get("usbdev_type")
            usb["bus"] = usb_params.get("pci_bus", "pci.0")

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

            if not self._has_device(usb["type"]):
                raise InstanceSpecError(
                    "usb device %s not available" % usb["type"])

            if self._has_option("device"):
                usb["id"] = "usb-%s" % usb_dev
                usb_props["bus"] = usb_params.get("usbdev_bus")
                usb_props["port"] = usb_params.get("usbdev_port")
                usb_props["serial"] = usb_params.get("usbdev_serial")
                usb["bus"] = usb_params.get("usb_controller")
            else:
                if "tablet" in usb["type"]:
                    usb["type"] = "usb-%s" % usb_dev
                else:
                    usb["type"] = "missing-usb-%s" % usb_dev
                    LOG.error(
                        "This qemu supports only tablet device; ignoring" " %s",
                        usb_dev
                    )

            usb["props"] = usb_props
            usbs.append(usb)

        return usbs

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
                    # "controllers": [ # TODO: should move to the controller spec,
                                            but it is hard to do that since the
                                            HBA controllers are created by dynamically
                    #                 {
                    #                 "id": str,
                    #                 "bus": str,
                    #                 "type": str,
                    #                 "props": dict
                    #                 },
                    #             ]
                    "source": {
                                "id": str, #volume id
                                "type": str
                                "props": str,
                                "format": {
                                            "type": str
                                            "props": dict
                                        },
                                "backend": {
                                            "type": str,
                                            "props": dict,
                                        },
                                "slice":{
                                        "type": str
                                        "props": dict
                                    },
                                "auth": {
                                        "type": str
                                        "props": dict
                                },
                                "encrypt": {
                                        "type": str
                                        "props": dict
                                    },
                                "tls": {
                                        "type": str
                                        "props": dict
                                },
                                "httpcookie": {
                                        "type": str
                                        "props": dict
                                },
                            },
                    "filter": [
                            {
                              "type": str,
                              "props": dict
                            },
                    ]
                    "device": {
                                "id": str,
                                "type": str,
                                "bus": { # the hba controller spec
                                        "type": str,
                                        "props": dict,
                                        }
                                "props": dict
                            },
                    },
                 ]
        :rtype: list
        """
        def __define_spec_by_variables(
            name,
            filename,
            pci_bus,
            index=None,
            fmt=None,
            cache=None,
            werror=None,
            rerror=None,
            serial=None,
            snapshot=None,
            boot=None,
            blkdebug=None,
            bus=None,
            unit=None,
            port=None,
            bootindex=None,
            removable=None,
            min_io_size=None,
            opt_io_size=None,
            physical_block_size=None,
            logical_block_size=None,
            readonly=None,
            scsiid=None,
            lun=None,
            aio=None,
            strict_mode=None,
            media=None,
            imgfmt=None,
            pci_addr=None,
            scsi_hba=None,
            iothread=None,
            blk_extra_params=None,
            scsi=None,
            drv_extra_params=None,
            num_queues=None,
            bus_extra_params=None,
            force_fmt=None,
            image_encryption=None,
            image_access=None,
            external_data_file=None,
            image_throttle_group=None,
            image_auto_readonly=None,
            image_discard=None,
            image_copy_on_read=None,
            image_iothread_vq_mapping=None,
            slices_info=None,
        ):
            # def _get_access_tls_creds(image_access):
            #     """Get all tls-creds objects of the image and its backing images"""
            #     tls_creds = []
            #     if image_access is not None:
            #         creds_list = []
            #         if image_access.image_backing_auth:
            #             creds_list.extend(
            #                 image_access.image_backing_auth.values())
            #         if image_access.image_auth:
            #             creds_list.append(image_access.image_auth)
            #
            #         for creds in creds_list:
            #             if creds.storage_type == "nbd":
            #                 if creds.tls_creds:
            #                     tls_creds.append(creds)
            #
            #     return tls_creds
            #
            # def _get_access_secrets(image_access):
            #     """Get all secret objects of the image and its backing images"""
            #     secrets = []
            #     if image_access is not None:
            #         access_info = []
            #
            #         # backing images' access objects
            #         if image_access.image_backing_auth:
            #             access_info.extend(
            #                 image_access.image_backing_auth.values())
            #
            #         # image's access object
            #         if image_access.image_auth is not None:
            #             access_info.append(image_access.image_auth)
            #
            #         for access in access_info:
            #             if access.storage_type == "ceph":
            #                 # Now we use 'key-secret' for both -drive and -blockdev,
            #                 # but for -drive, 'password-secret' also works, add an
            #                 # option in cfg file to enable 'password-secret' in future
            #                 if access.data:
            #                     secrets.append((access, "key"))
            #             elif access.storage_type == "iscsi-direct":
            #                 if Flags.BLOCKDEV in self.caps:
            #                     # -blockdev: only password-secret is supported
            #                     if access.data:
            #                         secrets.append((access, "password"))
            #                 else:
            #                     # -drive: u/p included in the filename
            #                     pass
            #             elif access.storage_type == "curl":
            #                 if access.cookie:
            #                     secrets.append((access.cookie, "cookie"))
            #
            #                 if Flags.BLOCKDEV in self.caps:
            #                     # -blockdev requires password-secret while
            #                     # -drive includes u/p in the filename
            #                     if access.data:
            #                         secrets.append((access, "password"))
            #
            #     return secrets

            disk = dict()
            disk_props = dict()

            # controller = dict()
            # controller_props = dict()

            source = dict()
            source_props = dict()
            source_format = dict()
            source_format_props = dict()
            source_backend = dict()
            source_backend_props = dict()
            source_slice = dict
            source_slice_props = dict()
            source_auth = dict()
            source_auth_props = dict()
            source_encrypt = dict()
            source_encrypt_props = dict()
            source_tls = dict()
            source_tls_props = dict()

            source_filters = list()
            source_filter = dict()
            source_filter_props = dict()

            device = dict()
            device_bus = dict()
            device_bus_props = dict()
            device_bus["props"] = device_bus_props
            device_props = dict()

            #
            # Parse params
            #
            # devices = []  # All related devices


            # FIXME: skip it
            # add required secret objects for image
            # secret_obj = None
            # if image_encryption:
            #     for secret in image_encryption.image_key_secrets:
            #         devices.append(qdevices.QObject("secret"))
            #         devices[-1].set_param("id", secret.aid)
            #         devices[-1].set_param("data", secret.data)
            #     if image_encryption.key_secret:
            #         secret_obj = devices[-1]
            #
            # secret_info = []
            # image_secrets = _get_access_secrets(image_access)
            # for sec, sectype in image_secrets:
            #     # create and add all secret objects: -object secret
            #     devices.append(qdevices.QObject("secret"))
            #     devices[-1].set_param("id", sec.aid)
            #     devices[-1].set_param("format", sec.data_format)
            #
            #     if sectype == "password":
            #         devices[-1].set_param("file", sec.filename)
            #     elif sectype == "key" or sectype == "cookie":
            #         devices[-1].set_param("data", sec.data)
            #
            #     if sec.image == name:
            #         # only the top image should be associated
            #         # with its secure object
            #         secret_info.append((devices[-1], sectype))
            #
            # tls_creds = None
            # tls_creds_obj = None
            # creds_list = _get_access_tls_creds(image_access)
            # for creds in creds_list:
            #     # create and add all tls-creds objects
            #     devices.append(qdevices.QObject("tls-creds-x509"))
            #     devices[-1].set_param("id", creds.aid)
            #     devices[-1].set_param("endpoint", "client")
            #     devices[-1].set_param("dir", creds.tls_creds)
            #
            #     if creds.image == name:
            #         # only the top image should be associated
            #         # with its tls-creds object
            #         tls_creds_obj = devices[-1]
            #         tls_creds = creds
            #
            # iscsi_initiator = None
            # gluster_debug = None
            # gluster_logfile = None
            # gluster_peers = {}
            # reconnect_delay = None
            # curl_sslverify = None
            # curl_readahead = None
            # curl_timeout = None
            # access = image_access.image_auth if image_access else None
            # if access is not None:
            #     if access.storage_type == "iscsi-direct":
            #         iscsi_initiator = access.iscsi_initiator
            #     elif access.storage_type == "glusterfs-direct":
            #         gluster_debug = access.debug
            #         gluster_logfile = access.logfile
            #
            #         peers = []
            #         for peer in access.peers:
            #             if "path" in peer:
            #                 # access storage by unix domain socket
            #                 peers.append(
            #                     {"type": "unix", "path": peer["path"]})
            #             else:
            #                 # access storage by hostname/ip + port
            #                 peers.append(
            #                     {
            #                         "host": peer["host"],
            #                         "type": peer.get("type", "inet"),
            #                         "port": "%s" % peer.get("port", "0"),
            #                     }
            #                 )
            #         gluster_peers.update(
            #             {
            #                 "server.{i}.{k}".format(i=i + 1, k=k): v
            #                 for i, server in enumerate(peers)
            #                 for k, v in six.iteritems(server)
            #             }
            #         )
            #     elif access.storage_type == "nbd":
            #         reconnect_delay = access.reconnect_delay
            #     elif access.storage_type == "curl":
            #         curl_sslverify = access.sslverify
            #         curl_timeout = access.timeout
            #         curl_readahead = access.readahead

            use_device = self._has_option("device")
            if fmt == "scsi":  # fmt=scsi force the old version of devices
                LOG.warning(
                    "'scsi' drive_format is deprecated, please use the "
                    "new lsi_scsi type for disk %s",
                    name,
                )
                use_device = False
            if not fmt:
                use_device = False
            if fmt == "floppy" and not self._has_option("global"):
                use_device = False

            if strict_mode is None:
                strict_mode = self.strict_mode
            if strict_mode:  # Force default variables
                if cache is None:
                    cache = "none"
                if removable is None:
                    removable = "yes"
                if aio is None:
                    aio = "native"
                if media is None:
                    media = "disk"
            else:  # Skip default variables
                if media != "cdrom":  # ignore only 'disk'
                    media = None

            if "[,boot=on|off]" not in self._qemu_help:
                if boot in ("yes", "on", True):
                    bootindex = "1"
                boot = None

            bus = self._none_or_int(bus)  # First level
            unit = self._none_or_int(unit)  # Second level
            port = self._none_or_int(port)  # Third level
            # Compatibility with old params - scsiid, lun
            if scsiid is not None:
                LOG.warning(
                    "drive_scsiid param is obsolete, use drive_unit " "instead (disk %s)",
                    name,
                )
                unit = self._none_or_int(scsiid)
            if lun is not None:
                LOG.warning(
                    "drive_lun param is obsolete, use drive_port instead " "(disk %s)",
                    name
                )
                port = self._none_or_int(lun)
            if pci_addr is not None and fmt == "virtio":
                LOG.warning(
                    "drive_pci_addr is obsolete, use drive_bus instead " "(disk %s)",
                    name
                )
                bus = self._none_or_int(pci_addr)

            arch = self._node.proxy.platform.get_arch()

            # Define the controller spec
            #
            # HBA
            # fmt: ide, scsi, virtio, scsi-hd, ahci, usb1,2,3 + hba
            # device: ide-drive, usb-storage, scsi-hd, scsi-cd, virtio-blk-pci
            # bus: ahci, virtio-scsi-pci, USB
            #
            if not use_device:
                pass
                # TODO: support the drive mode
                # if fmt and (
                #         fmt == "scsi"
                #         or (
                #                 fmt.startswith("scsi")
                #                 and (
                #                         scsi_hba == "lsi53c895a" or scsi_hba == "spapr-vscsi")
                #         )
                # ):
                #     if not (bus is None and unit is None and port is None):
                #         LOG.warning(
                #             "Using scsi interface without -device "
                #             "support; ignoring bus/unit/port. (%s)",
                #             name,
                #         )
                #         source_props["bus"] = None
                #         source_props["unit"] = None
                #         source_props["port"] = None
                #     # In case we hotplug, lsi wasn't added during the startup hook
                #     if arch in ("ppc64", "ppc64le"):
                #         controller["type"] = "spapr-vscsi"
                #         controller["bus"] = None
                #         controller_props["bus"] = None
                #         controller_props["unit"] = None
                #         controller_props["port"] = None
                #     else:
                #         controller["type"] = "lsi53c895a"
                #         controller["bus"] = pci_bus
                #         controller_props["bus"] = None
                #         controller_props["unit"] = None
                #         controller_props["port"] = None
            elif fmt == "ide":
                if bus:
                    LOG.warning(
                        "ide supports only 1 hba, use drive_unit to set"
                        "ide.* for disk %s",
                        name,
                    )
                bus = unit
                device_bus["type"] = "ide"
            elif fmt == "ahci":
                pass
                # devices.extend(devs)
            elif fmt.startswith("scsi-"):
                if not scsi_hba:
                    scsi_hba = "virtio-scsi-pci"
                if scsi_hba != "virtio-scsi-pci":
                    num_queues = None
                addr_spec = None
                if scsi_hba == "lsi53c895a":
                    addr_spec = [8, 16384]
                elif scsi_hba.startswith("virtio"):
                    addr_spec = [256, 16384]
                    if scsi_hba == "virtio-scsi-device":
                        pci_bus = "virtio-bus"
                    elif scsi_hba == "virtio-scsi-ccw":
                        pci_bus = None
                elif scsi_hba == "spapr-vscsi":
                    addr_spec = [64, 32]
                    pci_bus = None
                device_bus["type"] = scsi_hba
                device_bus["bus"] = pci_bus
                # device_bus_props["bus"] = bus
                # device_bus_props["unit"] = unit
                # device_bus_props["port"] = port
                device_bus_props["num_queues"] = num_queues
                device_bus_props["addr_spec"] = addr_spec
                if bus_extra_params:
                    for extra_param in bus_extra_params.split(","):
                        key, value = extra_param.split("=")
                        device_bus_props[key] = value
                # devices.extend(_)
            elif fmt in ("usb1", "usb2", "usb3"):
                if bus:
                    LOG.warning(
                        "Manual setting of drive_bus is not yet supported"
                        " for usb disk %s",
                        name,
                    )
                    bus = None
                if fmt == "usb1":
                    pass
                    # dev_parent = {"type": "uhci"}
                    # if arch.ARCH in ("ppc64", "ppc64le"):
                    #     dev_parent = {"type": "ohci"}
                elif fmt == "usb2":
                    pass
                    # dev_parent = "ehci"
                elif fmt == "usb3":
                    pass
                    # dev_parent = {"type": "xhci"}
            elif fmt == "virtio":
                pass
                # dev_parent = pci_bus
            elif fmt == "virtio-blk-device":
                pass
                # dev_parent = {"type": "virtio-bus"}
            elif fmt == "virtio-blk-ccw":  # For IBM s390 platform
                pass
                # dev_parent = {"type": "virtual-css"}
            else:
                pass
                # dev_parent = {"type": fmt}

            # Define the source spec
            #
            # Drive mode:
            # -drive fmt or -drive fmt=none -device ...
            # Blockdev mode:
            # -blockdev node-name ... -device ...
            #
            if Flags.BLOCKDEV in self._qemu_caps:
                protocol_cls = qdevices.QBlockdevProtocolFile
                if not filename:
                    protocol_cls = qdevices.QBlockdevProtocolNullCo
                elif filename.startswith("iscsi:"):
                    protocol_cls = qdevices.QBlockdevProtocolISCSI
                elif filename.startswith("rbd:"):
                    protocol_cls = qdevices.QBlockdevProtocolRBD
                elif filename.startswith("gluster"):
                    protocol_cls = qdevices.QBlockdevProtocolGluster
                elif re.match(r"nbd(\+\w+)?://", filename):
                    protocol_cls = qdevices.QBlockdevProtocolNBD
                elif filename.startswith("nvme:"):
                    protocol_cls = qdevices.QBlockdevProtocolNVMe
                elif filename.startswith("ssh:"):
                    protocol_cls = qdevices.QBlockdevProtocolSSH
                elif filename.startswith("https:"):
                    protocol_cls = qdevices.QBlockdevProtocolHTTPS
                elif filename.startswith("http:"):
                    protocol_cls = qdevices.QBlockdevProtocolHTTP
                elif filename.startswith("ftps:"):
                    protocol_cls = qdevices.QBlockdevProtocolFTPS
                elif filename.startswith("ftp:"):
                    protocol_cls = qdevices.QBlockdevProtocolFTP
                elif filename.startswith("vdpa:"):
                    protocol_cls = qdevices.QBlockdevProtocolVirtioBlkVhostVdpa
                elif fmt in ("scsi-generic", "scsi-block"):
                    protocol_cls = qdevices.QBlockdevProtocolHostDevice
                elif blkdebug is not None:
                    protocol_cls = qdevices.QBlockdevProtocolBlkdebug

                if imgfmt == "qcow2":
                    format_cls = qdevices.QBlockdevFormatQcow2
                elif imgfmt == "raw" or media == "cdrom":
                    format_cls = qdevices.QBlockdevFormatRaw
                elif imgfmt == "luks":
                    format_cls = qdevices.QBlockdevFormatLuks
                elif imgfmt == "nvme":
                    format_cls = qdevices.QBlockdevFormatRaw
                elif imgfmt is None:
                    # use RAW type as the default
                    format_cls = qdevices.QBlockdevFormatRaw

                # vt_images = self._env.get_vm_images(self._name)
                # for image in vt_images:
                #     if image.tag == image_name:
                #         source["id"] = image.uuid
                #         image_info = vt_image.api.get_info(image.uuid)
                #         volume_id = image_info.get("volume_id")
                #         source["id"] = "volume1"
                # disk["source"] = "volume_%s" % image_name
                source["id"] = name
                source["type"] = protocol_cls.TYPE
                top_node = "protocol_node"

                need_format_node = format_cls is not qdevices.QBlockdevFormatRaw
                need_format_node |= Flags.BLOCKJOB_BACKING_MASK_PROTOCOL not in self._qemu_caps
                need_format_node |= slices_info is not None and bool(
                    slices_info.slices)
                format_node = None
                if need_format_node:
                    source_format["type"] = format_cls.TYPE
                    top_node = "format_node"
                # Add filter node
                if image_copy_on_read in ("yes", "on", "true"):
                    source_filter["type"] = qdevices.QBlockdevFilterCOR.TYPE
                    source_filters.append(source_filter)

                if image_throttle_group:
                    source_filter["type"] = qdevices.QBlockdevFilterThrottle.TYPE
                    source_filters.append(source_filter)
            # else: # FIXME: skip the drive mode
                # if self.has_hmp_cmd("__com.redhat_drive_add") and use_device:
                #     devices.append(qdevices.QRHDrive(name))
                # elif self.has_hmp_cmd("drive_add") and use_device:
                #     devices.append(qdevices.QHPDrive(name))
                # elif self.has_option("device"):
                #     devices.append(qdevices.QDrive(name, use_device))
                # else:  # very old qemu without 'addr' support
                #     devices.append(qdevices.QOldDrive(name, use_device))

            if Flags.BLOCKDEV in self._qemu_caps:
                for opt, val in zip(("serial", "boot"), (serial, boot)):
                    if val is not None:
                        LOG.warning(
                            "The command line option %s is not supported "
                            "on %s by -blockdev." % (opt, name)
                        )
                if media == "cdrom":
                    readonly = "on"

                if top_node == "protocol_node":
                    source_props["read-only"] = readonly
                elif top_node == "format_node":
                    source_format_props["read-only"] = readonly

                if top_node != "protocol_node":
                    source_props["auto-read-only"] = image_auto_readonly
                source_props["discard"] = image_discard

                if slices_info is not None and len(slices_info.slices) > 0:
                    source_format_props["offset"] = slices_info.slices[0].offset
                    source_format_props["size"] = slices_info.slices[0].size

                # if secret_obj:
                #     if source_format.get("type") == qdevices.QBlockdevFormatQcow2.TYPE:
                #         source_format_props["encrypt.format"] = image_encryption.format
                #         source_format_props["encrypt.key-secret"] = secret_obj.get_qid()
                #     elif source_format.get("type") == qdevices.QBlockdevFormatLuks.TYPE:
                #         source_format_props["key-secret"] = secret_obj.get_qid()

            # else: # FIXME: skip this part for drive mode
                # devices[-1].set_param("if", "none")
                # devices[-1].set_param("rerror", rerror)
                # devices[-1].set_param("werror", werror)
                # devices[-1].set_param("serial", serial)
                # devices[-1].set_param("boot", boot, bool)
                # devices[-1].set_param("snapshot", snapshot, bool)
                # devices[-1].set_param("readonly", readonly, bool)
                # if secret_obj:
                #     if imgfmt == "qcow2":
                #         devices[-1].set_param("encrypt.format",
                #                               image_encryption.format)
                #         devices[-1].set_param("encrypt.key-secret",
                #                               secret_obj.get_qid())
                #     elif imgfmt == "luks":
                #         devices[-1].set_param("key-secret",
                #                               secret_obj.get_qid())
            # FIXME: skip this part for drive mode
            # external_data_file_path = getattr(external_data_file,
            #                                   "image_filename", None)
            # if external_data_file_path:
            #     # by now we only support local files
            #     ext_data_file_driver = "file"
            #
            #     # check if the data file is a block device
            #     if ext_data_file_driver == "file":
            #         ext_data_file_mode = os.stat(
            #             external_data_file_path).st_mode
            #         if stat.S_ISBLK(ext_data_file_mode):
            #             ext_data_file_driver = "host_device"
            #     devices[-1].set_param("data-file.driver", ext_data_file_driver)
            #     devices[-1].set_param("data-file.filename",
            #                           external_data_file_path)

            if "aio" in self._qemu_help:
                if aio == "native" and snapshot == "yes":
                    LOG.warning("snapshot is on, fallback aio to threads.")
                    aio = "threads"
                if Flags.BLOCKDEV in self._qemu_caps:
                    if source.get("type") in (
                                    qdevices.QBlockdevProtocolFile,
                                    qdevices.QBlockdevProtocolHostDevice,
                                    qdevices.QBlockdevProtocolHostCdrom,
                            ):
                        source_props["aio"] = aio
                # FIXME: skip this part for drive mode
                # else:
                #     devices[-1].set_param("aio", aio)
                if aio == "native":
                    # Since qemu 2.6, aio=native has no effect without
                    # cache.direct=on or cache=none, It will be error out.
                    # Please refer to qemu commit d657c0c.
                    cache = cache not in ["none",
                                          "directsync"] and "none" or cache
            # Forbid to specify the cache mode for empty drives.
            # More info from qemu commit 91a097e74.
            if not filename:
                cache = None
            elif filename.startswith("nvme://"):
                # NVMe controller doesn't support write cache configuration
                cache = "writethrough"
            if Flags.BLOCKDEV in self._qemu_caps:
                if filename:
                    file_opts = qemu_storage.filename_to_file_opts(filename)
                    for key, value in six.iteritems(file_opts):
                        source_props[key] = value
                #
                # for access_secret_obj, secret_type in secret_info:
                #     if secret_type == "password":
                #         protocol_node.set_param(
                #             "password-secret", access_secret_obj.get_qid()
                #         )
                #     elif secret_type == "key":
                #         protocol_node.set_param("key-secret",
                #                                 access_secret_obj.get_qid())
                #     elif secret_type == "cookie":
                #         protocol_node.set_param(
                #             "cookie-secret", access_secret_obj.get_qid()
                #         )
                #
                # if tls_creds is not None:
                #     protocol_node.set_param("tls-creds",
                #                             tls_creds_obj.get_qid())
                # if reconnect_delay is not None:
                #     protocol_node.set_param("reconnect-delay",
                #                             int(reconnect_delay))
                # if iscsi_initiator:
                #     protocol_node.set_param("initiator-name", iscsi_initiator)
                # if gluster_debug:
                #     protocol_node.set_param("debug", int(gluster_debug))
                # if gluster_logfile:
                #     protocol_node.set_param("logfile", gluster_logfile)
                # if curl_sslverify:
                #     protocol_node.set_param("sslverify", curl_sslverify)
                # if curl_readahead:
                #     protocol_node.set_param("readahead", curl_readahead)
                # if curl_timeout:
                #     protocol_node.set_param("timeout", curl_timeout)
                # for key, value in six.iteritems(gluster_peers):
                #     protocol_node.set_param(key, value)

                if not cache:
                    direct, no_flush = (None, None)
                else:
                    direct, no_flush = (
                        self.cache_map[cache]["cache.direct"],
                        self.cache_map[cache]["cache.no-flush"],
                    )
                source_props["cache.direct"] = direct
                source_format_props["cache.direct"] = direct
                source_props["cache.no-flush"] = no_flush
                source_format_props["cache.no-flush"] = no_flush

                # if top_node is not protocol_node:
                #     top_node.set_param("file", protocol_node.get_qid())
            # FIXME: skip this part for drive mode
            # else:
            #     devices[-1].set_param("cache", cache)
            #     devices[-1].set_param("media", media)
            #     devices[-1].set_param("format", imgfmt)
            #     if blkdebug is not None:
            #         devices[-1].set_param("file", "blkdebug:%s:%s" % (
            #         blkdebug, filename))
            #     else:
            #         devices[-1].set_param("file", filename)
            #
            #     for access_secret_obj, secret_type in secret_info:
            #         if secret_type == "password":
            #             devices[-1].set_param(
            #                 "file.password-secret", access_secret_obj.get_qid()
            #             )
            #         elif secret_type == "key":
            #             devices[-1].set_param(
            #                 "file.key-secret", access_secret_obj.get_qid()
            #             )
            #         elif secret_type == "cookie":
            #             devices[-1].set_param(
            #                 "file.cookie-secret", access_secret_obj.get_qid()
            #             )
            #
            #     if tls_creds is not None:
            #         devices[-1].set_param("file.tls-creds",
            #                               tls_creds_obj.get_qid())
            #     if reconnect_delay is not None:
            #         devices[-1].set_param("file.reconnect-delay",
            #                               int(reconnect_delay))
            #     if iscsi_initiator:
            #         devices[-1].set_param("file.initiator-name",
            #                               iscsi_initiator)
            #     if gluster_debug:
            #         devices[-1].set_param("file.debug", int(gluster_debug))
            #     if gluster_logfile:
            #         devices[-1].set_param("file.logfile", gluster_logfile)
            #     if curl_sslverify:
            #         devices[-1].set_param("file.sslverify", curl_sslverify)
            #     if curl_readahead:
            #         devices[-1].set_param("file.readahead", curl_readahead)
            #     if curl_timeout:
            #         devices[-1].set_param("file.timeout", curl_timeout)

            if drv_extra_params:
                drv_extra_params = (
                    _.split("=", 1) for _ in drv_extra_params.split(",") if _
                )
                for key, value in drv_extra_params:
                    if Flags.BLOCKDEV in self._qemu_caps:
                        if key == "discard":
                            value = re.sub("on", "unmap",
                                           re.sub("off", "ignore", value))
                        if key in ("cache-size",):
                            source_props[key] = None
                        else:
                            source_props[key] = value
                        if source_format is not None:
                            source_format_props[key] = value
                            # suppress key if format_node presents
                            if key in ("detect-zeroes",):
                                source_props[key] = None
                    # FIXME: skip this part for drive mode
                    # else:
                    #     devices[-1].set_param(key, value)

            # TODO: support the drive mode
            # if not use_device:
            #     if fmt and fmt.startswith("scsi-"):
            #         if scsi_hba == "lsi53c895a" or scsi_hba == "spapr-vscsi":
            #             fmt = "scsi"  # Compatibility with the new scsi
            #     if fmt and fmt not in (
            #             "ide",
            #             "scsi",
            #             "sd",
            #             "mtd",
            #             "floppy",
            #             "pflash",
            #             "virtio",
            #     ):
            #         raise virt_vm.VMDeviceNotSupportedError(self.vmname, fmt)
            #     devices[-1].set_param("if",
            #                           fmt)  # overwrite previously set None
            #     if not fmt:  # When fmt unspecified qemu uses ide
            #         fmt = "ide"
            #     devices[-1].set_param("index", index)
            #     if fmt == "ide":
            #         devices[-1].parent_bus = (
            #         {"type": fmt.upper(), "atype": fmt},)
            #     elif fmt == "scsi":
            #         if arch.ARCH in ("ppc64", "ppc64le"):
            #             devices[-1].parent_bus = (
            #             {"atype": "spapr-vscsi", "type": "SCSI"},)
            #         else:
            #             devices[-1].parent_bus = (
            #             {"atype": "lsi53c895a", "type": "SCSI"},)
            #     elif fmt == "floppy":
            #         devices[-1].parent_bus = ({"type": fmt},)
            #     elif fmt == "virtio":
            #         devices[-1].set_param("addr", pci_addr)
            #         devices[-1].parent_bus = (pci_bus,)
            #     if not media == "cdrom":
            #         LOG.warning(
            #             "Using -drive fmt=xxx for %s is unsupported "
            #             "method, false errors might occur.",
            #             name,
            #         )
            #     disk["type"] = media
            #     return disk
            disk["id"] = name
            disk["type"] = media

            # Define the device spec
            #
            # Device
            #
            device["id"] = name
            # FIXME: workaround for this part by using dev_parent as the device bus
            device["bus"] = device_bus
            if fmt in ("ide", "ahci"):
                if not self._has_device("ide-hd"):
                    device["type"] = "ide-drive"
                elif media == "cdrom":
                    device["type"] = "ide-cd"
                else:
                    device["type"] = "ide-hd"
                device_props["unit"] = port
            elif fmt and fmt.startswith("scsi-"):
                device["type"] = fmt
                device_props["scsi-id"] = unit
                device_props["lun"] = unit
                device_props["removable"] = removable

                if strict_mode:
                    device_props["channel"] = 0

            elif fmt == "virtio":
                device["type"] = "virtio-blk-pci"
                device_props["scsi"] = scsi
                if bus is not None:
                    device_props["addr"] = bus
                    bus = None
                # TODO: support it in the future
                # if iothread:
                #     try:
                #         iothread = self.allocate_iothread(iothread, devices[-1])
                #     except TypeError:
                #         pass
                #     else:
                #         if iothread and iothread not in self:
                #             devices.insert(-2, iothread)
            elif fmt in ("usb1", "usb2", "usb3"):
                device["type"] = "usb-storage"
                device_props["port"] = unit
                device_props["removable"] = removable
            elif fmt == "floppy":
                device["type"] = "floppy"
                device_props["unit"] = unit
                device_bus["type"] = "floppy"
                device_bus["id"] = "drive_%s" % name

            else:
                LOG.warning("Using default device handling (disk %s)", name)
                device["type"] = fmt
            if force_fmt:
                LOG.info("Force to use %s for the device" % force_fmt)
                device["type"] = force_fmt
            # Get the supported options
            options = self._node.proxy.virt.tools.qemu.get_help_info("-device %s," % device["type"])
            device_props["bus"] = bus # 1st level of disk location (index of bus) ($int), bus:unit:port
            device_props["drive"] = "drive_%s" % name
            device_props["logical_block_size"] = logical_block_size
            device_props["physical_block_size"] = physical_block_size
            device_props["min_io_size"] = min_io_size
            device_props["opt_io_size"] = opt_io_size
            device_props["bootindex"] = bootindex
            if Flags.BLOCKDEV in self._qemu_caps:
                if source["type"] == qdevices.QBlockdevProtocolHostDevice.TYPE:
                    self.cache_map[cache]["write-cache"] = None
                write_cache = None if not cache else self.cache_map[cache]["write-cache"]
                device_props["write-cache"] = write_cache
                if "scsi-generic" == fmt:
                    rerror, werror = (None, None)
                device_props["rerror"] = rerror
                device_props["werror"] = werror
            if "serial" in options:
                device_props["serial"] = serial
                if need_format_node:
                    source_format_props["serial"] = serial
                source_props["serial"] = serial
            if blk_extra_params:
                blk_extra_params = (
                    _.split("=", 1) for _ in blk_extra_params.split(",") if _
                )
                for key, value in blk_extra_params:
                    device_props[key] = value
            # if self.is_dev_iothread_vq_supported(devices[-1]):
            #     if num_queues:
            #         devices[-1].set_param("num-queues", num_queues)
            #     # add iothread-vq-mapping if available
            #     if image_iothread_vq_mapping:
            #         val = []
            #         for item in image_iothread_vq_mapping.strip().split(" "):
            #             allocated_iothread = self.allocate_iothread_vq(
            #                 item.split(":")[0], devices[-1]
            #             )
            #             mapping = {"iothread": allocated_iothread.get_qid()}
            #             if len(item.split(":")) == 2:
            #                 vqs = [int(_) for _ in item.split(":")[-1].split(",")]
            #                 mapping["vqs"] = vqs
            #             val.append(mapping)
            #         # FIXME: The reason using set_param() is that the format(
            #         #  Example: iothread0:0,1,2 ) can NOT be set by
            #         #  Devcontainer.insert() appropriately since the contents
            #         #  following after colon are lost.
            #         if ":" in image_iothread_vq_mapping:
            #             devices[-1].set_param("iothread-vq-mapping", val)
            #
            #     if isinstance(
            #         self.iothread_manager, vt_iothread.MultiPeerRoundRobinManager
            #     ):
            #         mapping = self.iothread_manager.pci_dev_iothread_vq_mapping
            #         if devices[-1].get_qid() in mapping:
            #             num_iothread = len(mapping[devices[-1].get_qid()])
            #             for i in range(num_iothread):
            #                 iothread = self.allocate_iothread_vq("auto", devices[-1])
            #                 iothread.iothread_vq_bus.insert(devices[-1])
            #     elif isinstance(self.iothread_manager, vt_iothread.FullManager):
            #         iothreads = self.allocate_iothread_vq("auto", devices[-1])
            #         if iothreads:
            #             for ioth in iothreads:
            #                 ioth.iothread_vq_bus.insert(devices[-1])
            # controller["props"] = controller_props
            # disk["controller"] = controller

            source["props"] = source_props

            source_format["props"] = source_format_props
            source["format"] = source_format

            disk["source"] = source

            device["bus"] = device_bus
            device["props"] = device_props
            disk["device"] = device

            return disk

        disks = []
        for image_name in self._params.objects("images"):
            media = "disk"
            image_id = vt_imgr.query_image(image_name, self._name)
            image_info = vt_imgr.get_image_info(image_id)
            # FIXME: Use qemu_devices for handling indexes
            image_params = self._params.object_params(image_name)
            if image_params.get("boot_drive") == "no":
                continue
            if self._params.get("index_enable") == "yes":
                drive_index = image_params.get("drive_index")
                if drive_index:
                    index = drive_index
                else:
                    self.last_driver_index = self._get_index(self.last_driver_index)
                    index = str(self.last_driver_index)
                    self.last_driver_index += 1
            else:
                index = None
            image_bootindex = None
            image_boot = image_params.get("image_boot")
            if not re.search("boot=on\|off", self._qemu_help, re.MULTILINE):
                if image_boot in ["yes", "on", True]:
                    image_bootindex = str(self.last_boot_index)
                    self.last_boot_index += 1
                image_boot = "unused"
                image_bootindex = image_params.get("bootindex", image_bootindex)
            else:
                if image_boot in ["yes", "on", True]:
                    if self.last_boot_index > 0:
                        image_boot = False
                    self.last_boot_index += 1
            if "virtio" in image_params.get(
                "drive_format", ""
            ) or "virtio" in image_params.get("scsi_hba", ""):
                pci_bus = self._get_pci_bus(image_params, "disk", True)
            else:
                pci_bus = self._get_pci_bus(image_params, "disk", False)

            # data_root = data_dir.get_data_dir()
            # shared_dir = os.path.join(data_root, "shared")
            drive_format = image_params.get("drive_format")
            scsi_hba = image_params.get("scsi_hba", "virtio-scsi-pci")
            if drive_format == "virtio":  # translate virtio to ccw/device
                machine_type = image_params.get("machine_type")
                if "s390" in machine_type:  # s390
                    drive_format = "virtio-blk-ccw"
                elif "mmio" in machine_type:  # mmio-based machine
                    drive_format = "virtio-blk-device"
            if scsi_hba == "virtio-scsi-pci":
                if "mmio" in image_params.get("machine_type"):
                    scsi_hba = "virtio-scsi-device"
                elif "s390" in image_params.get("machine_type"):
                    scsi_hba = "virtio-scsi-ccw"
            # FIXME: skip this part
            # image_encryption = storage.ImageEncryption.encryption_define_by_params(
            #     image_name, image_params
            # )
            #
            # # all access information for the logical image
            # image_access = storage.ImageAccessInfo.access_info_define_by_params(
            #     image_name, image_params
            # )
            image_encryption = None
            image_access = None

            # image_base_dir = image_params.get("images_base_dir", data_root)
            # image_filename = storage.get_image_filename(image_params,
            #                                             image_base_dir)
            image_id = vt_imgr.query_image(image_name, self._name)
            image_uri = vt_imgr.get_image_info(image_id, f"spec.virt-images.{image_name}.spec.volume.spec.uri")
            image_filename = image_uri.get("uri")
            imgfmt = image_params.get("image_format")
            if (
                    image_filename.startswith("vdpa://")
                    and image_params.get("image_snapshot") == "yes"
            ):
                raise NotImplementedError(
                    "vdpa does NOT support the snapshot!")
            # FIXME: skip this part
            # if Flags.BLOCKDEV in self.caps and image_params.get(
            #         "image_snapshot") == "yes":
            #     # FIXME: Most of attributes for the snapshot should be got from the
            #     #        base image's metadata, not from the Cartesian parameter,
            #     #        so we need to get the base image object, and then use it
            #     #        to create the snapshot.
            #     sn_params = Params()
            #     for k, v in image_params.items():
            #         sn_params["%s_%s" % (k, image_name)] = v
            #     sn = "vl_%s_%s" % (self.vmname, image_name)
            #     sn_params["image_chain"] = "%s %s" % (image_name, sn)
            #     sn_params["image_name"] = sn
            #     # Empty the image_size parameter so that qemu-img will align the
            #     # size of the snapshot to the base image
            #     sn_params["image_size"] = ""
            #     sn_img = qemu_storage.QemuImg(sn_params,
            #                                   data_dir.get_data_dir(), sn)
            #     image_filename = sn_img.create(sn_params)[0]
            #     os.chmod(image_filename, stat.S_IRUSR | stat.S_IWUSR)
            #     LOG.info(
            #         "'snapshot=on' is not supported by '-blockdev' but "
            #         "requested from the image '%s', imitating the behavior "
            #         "of '-drive' to keep compatibility",
            #         image_name,
            #     )
            #     self.temporary_image_snapshots.add(image_filename)
            #     image_encryption = storage.ImageEncryption.encryption_define_by_params(
            #         sn, sn_params
            #     )
            #     imgfmt = "qcow2"
            #
            # FIXME: skip this part
            # # external data file
            # ext_data_file = storage.QemuImg.external_data_file_defined_by_params(
            #     image_params, data_root, image_name
            # )
            #
            # slices_info = storage.ImageSlicesInfo.slices_info_define_by_params(
            #     image_name, image_params
            # )
            ext_data_file = None
            slices_info = None

            disks.append(__define_spec_by_variables(
                image_name,
                image_filename,
                pci_bus,
                index,
                drive_format,
                image_params.get("drive_cache"),
                image_params.get("drive_werror"),
                image_params.get("drive_rerror"),
                image_params.get("drive_serial"),
                image_params.get("image_snapshot"),
                image_boot,
                # storage.get_image_blkdebug_filename(image_params, shared_dir),
                None,
                image_params.get("drive_bus"),
                image_params.get("drive_unit"),
                image_params.get("drive_port"),
                image_bootindex,
                image_params.get("removable"),
                image_params.get("min_io_size"),
                image_params.get("opt_io_size"),
                image_params.get("physical_block_size"),
                image_params.get("logical_block_size"),
                image_params.get("image_readonly"),
                image_params.get("drive_scsiid"),
                image_params.get("drive_lun"),
                image_params.get("image_aio"),
                image_params.get("strict_mode") == "yes",
                media,
                imgfmt,
                image_params.get("drive_pci_addr"),
                scsi_hba,
                image_params.get("image_iothread"),
                image_params.get("blk_extra_params"),
                image_params.get("virtio-blk-pci_scsi"),
                image_params.get("drv_extra_params"),
                image_params.get("num_queues"),
                image_params.get("bus_extra_params"),
                image_params.get("force_drive_format"),
                image_encryption,
                image_access,
                ext_data_file,
                image_params.get("image_throttle_group"),
                image_params.get("image_auto_readonly"),
                image_params.get("image_discard"),
                image_params.get("image_copy_on_read"),
                image_params.get("image_iothread_vq_mapping"),
                slices_info,)
            )

        # for floppy_name in self._params.objects("floppies"):
        #     disks.append(__define_spec_by_variables(
        #         floppy_name,
        #         filename,
        #         pci_bus,
        #         index=None,
        #         fmt=None,
        #         cache=None,
        #         werror=None,
        #         rerror=None,
        #         serial=None,
        #         snapshot=None,
        #         boot=None,
        #         blkdebug=None,
        #         bus=None,
        #         unit=None,
        #         port=None,
        #         bootindex=None,
        #         removable=None,
        #         min_io_size=None,
        #         opt_io_size=None,
        #         physical_block_size=None,
        #         logical_block_size=None,
        #         readonly=None,
        #         scsiid=None,
        #         lun=None,
        #         aio=None,
        #         strict_mode=None,
        #         media=None,
        #         imgfmt=None,
        #         pci_addr=None,
        #         scsi_hba=None,
        #         iothread=None,
        #         blk_extra_params=None,
        #         scsi=None,
        #         drv_extra_params=None,
        #         num_queues=None,
        #         bus_extra_params=None,
        #         force_fmt=None,
        #         image_encryption=None,
        #         image_access=None,
        #         external_data_file=None,
        #         image_throttle_group=None,
        #         image_auto_readonly=None,
        #         image_discard=None,
        #         image_copy_on_read=None,
        #         image_iothread_vq_mapping=None,
        #         slices_info=None, )
        #     )

        # for cdrom in self._params.objects("cdroms"):
        #     disks.append(__define_spec_by_variables(
        #         cdrom,
        #         filename,
        #         pci_bus,
        #         index=None,
        #         fmt=None,
        #         cache=None,
        #         werror=None,
        #         rerror=None,
        #         serial=None,
        #         snapshot=None,
        #         boot=None,
        #         blkdebug=None,
        #         bus=None,
        #         unit=None,
        #         port=None,
        #         bootindex=None,
        #         removable=None,
        #         min_io_size=None,
        #         opt_io_size=None,
        #         physical_block_size=None,
        #         logical_block_size=None,
        #         readonly=None,
        #         scsiid=None,
        #         lun=None,
        #         aio=None,
        #         strict_mode=None,
        #         media=None,
        #         imgfmt=None,
        #         pci_addr=None,
        #         scsi_hba=None,
        #         iothread=None,
        #         blk_extra_params=None,
        #         scsi=None,
        #         drv_extra_params=None,
        #         num_queues=None,
        #         bus_extra_params=None,
        #         force_fmt=None,
        #         image_encryption=None,
        #         image_access=None,
        #         external_data_file=None,
        #         image_throttle_group=None,
        #         image_auto_readonly=None,
        #         image_discard=None,
        #         image_copy_on_read=None,
        #         image_iothread_vq_mapping=None,
        #         slices_info=None,)
        #     )

        return disks

    def _define_spec_encryptions(self):
        return []

    def _define_spec_auths(self):
        return []

    def _define_spec_secrets(self):
        return []

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
                    "type": str,
                    "bus": str,
                    "props": dict,
                    },
                 ]
        :rtype: list
        """
        vsocks = []
        _vsocks = self._params.objects("vsocks")
        if _vsocks:
            min_cid = 3
            for _vsock in _vsocks:
                vsock = dict()
                vsock_props = dict()
                vsock["props"] = vsock_props

                guest_cid = self._node.proxy.network.get_guest_cid(min_cid)
                vsock["id"] = _vsock

                if "-mmio:" in self._params.get("machine_type"):
                    vsock["type"] = "vhost-vsock-device"
                elif self._params.get("machine_type").startswith("s390"):
                    vsock["type"] = "vhost-vsock-ccw"
                else:
                    vsock["type"] = "vhost-vsock-pci"

                vsock["bus"] = self._params.get("pci_bus")
                vsock_props["guest-cid"] = guest_cid
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
        spec["controllers"] = self._define_spec_controllers()
        spec["machine"] = self._define_spec_machine(spec["controllers"])
        spec["firmware"] = self._define_spec_firmware(spec["machine"])  # TODO
        spec["launch_security"] = self._define_spec_launch_security()
        spec["iommu"] = self._define_spec_iommu()
        spec["vga"] = self._define_spec_vga()
        spec["watchdog"] = self._define_spec_watchdog()
        spec["memory"] = self._define_spec_memory()
        spec["cpu"] = self._define_spec_cpu()
        spec["numa"] = self._define_spec_numa()  # TODO: support the NUMA spec
        spec["soundcards"] = self._define_spec_soundcards()
        spec["monitors"] = self._define_spec_monitors()
        spec["panics"] = self._define_spec_panics()
        spec["vmcoreinfo"] = self._define_spec_vmcoreinfo()
        spec["serials"] = self._define_spec_serials()  # TODO: refactor this
        spec["rngs"] = self._define_spec_rngs()
        spec["debugs"] = self._define_spec_debugs()
        spec["usbs"] = self._define_spec_usbs()
        spec["iothreads"] = self._define_spec_iothreads()
        spec["throttle_groups"] = self._define_spec_throttle_groups()
        spec["disks"] = self._define_spec_disks()
        spec["encryptions"] = self._define_spec_encryptions() # TODO: support the encryptions spec
        spec["auths"] = self._define_spec_auths()  # TODO: support the auths spec
        spec["secrets"] = self._define_spec_secrets()  # TODO: support the secrets spec
        spec["filesystems"] = self._define_spec_filesystems()
        spec["nets"] = self._define_spec_nets()  # TODO: support the nets spec
        spec["vsocks"] = self._define_spec_vsocks()
        spec["os"] = self._define_spec_os()
        spec["graphics"] = self._define_spec_graphics()
        spec["rtc"] = self._define_spec_rtc()
        spec["tpms"] = self._define_spec_tpms()
        spec["power_management"] = self._define_spec_power_management()
        spec["inputs"] = self._define_spec_inputs()
        spec["balloons"] = self._define_spec_balloons()
        spec["keyboard_layout"] = self._define_spec_keyboard_layout()
        spec_str = json.dumps(spec, indent=4, separators=(",", ": "))
        LOG.debug(f"The instance spec: \n{spec_str}")
        return spec
