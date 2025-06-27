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
import os

from virttest.qemu_capabilities import Flags

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecFirmware(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecFirmware, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
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
        machine_type = self._params.get("machine_type")
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

    def _parse_params(self):
        self._spec.update({"firmware": self._define_spec()})
