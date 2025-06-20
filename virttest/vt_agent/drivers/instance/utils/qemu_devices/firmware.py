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
# Copyright: Red Hat Inc. 2025 and Avocado contributors
# Authors: Yongxue Hong <yhong@redhat.com>


import os
import shutil

from virttest.qemu_devices import qdevices

from vt_agent.core import data_dir as core_data_dir


def create_firmware_devices(firmware):
    # FIXME:
    devs = []
    firmware_type = firmware.get("type")
    firmware_code = firmware.get("code")
    pflash_code_format = firmware_code.get("format")
    pflash_code_path = firmware_code.get("path")
    pflash0, pflash1 = (firmware_type + "_code", firmware_type + "_vars")
    # Firmware code file
    protocol_pflash0 = qdevices.QBlockdevProtocolFile(pflash0)
    if pflash_code_format == "raw":
        format_pflash0 = qdevices.QBlockdevFormatRaw(pflash0)
    elif pflash_code_format == "qcow2":
        format_pflash0 = qdevices.QBlockdevFormatQcow2(pflash0)
    else:
        raise NotImplementedError(
            f"pflash does not support {pflash_code_format} "
            f"format firmware code file yet."
        )
    format_pflash0.add_child_node(protocol_pflash0)
    protocol_pflash0.set_param("driver", "file")
    protocol_pflash0.set_param("filename", pflash_code_path)
    protocol_pflash0.set_param("auto-read-only", "on")
    protocol_pflash0.set_param("discard", "unmap")
    format_pflash0.set_param("read-only", "on")
    format_pflash0.set_param("file", protocol_pflash0.get_qid())
    devs.extend([protocol_pflash0, format_pflash0])
    # machine_params["pflash0"] = format_pflash0.params["node-name"]

    # TODO:
    # else:
    #     devs.append(qdevices.QDrive(pflash0, use_device=False))
    #     devs[-1].set_param("if", "pflash")
    #     devs[-1].set_param("format", pflash_code_format)
    #     devs[-1].set_param("readonly", "on")
    #     devs[-1].set_param("file", pflash_code_path)

    # Firmware vars file
    firmware_vars = firmware.get("vars")
    pflash_vars_format = firmware_vars.get("format")
    pflash_vars_src_path = firmware_vars.get("src_path")
    pflash_vars_path = firmware_vars.get("dst_path")
    if not os.path.isabs(pflash_vars_path):
        pflash_vars_path = os.path.join(core_data_dir.get_data_dir(),
                                        pflash_vars_path)
    if firmware_vars:
        if firmware_vars.get("restore"):
            shutil.copy2(pflash_vars_src_path, pflash_vars_path)

        protocol_pflash1 = qdevices.QBlockdevProtocolFile(pflash1)
        if pflash_vars_format == "raw":
            format_pflash1 = qdevices.QBlockdevFormatRaw(pflash1)
        elif pflash_vars_format == "qcow2":
            format_pflash1 = qdevices.QBlockdevFormatQcow2(pflash1)
        else:
            raise NotImplementedError(
                f"pflash does not support {pflash_vars_format} "
                f"format firmware vars file yet."
            )
        format_pflash1.add_child_node(protocol_pflash1)
        protocol_pflash1.set_param("driver", "file")
        protocol_pflash1.set_param("filename", pflash_vars_path)
        protocol_pflash1.set_param("auto-read-only", "on")
        protocol_pflash1.set_param("discard", "unmap")
        format_pflash1.set_param("read-only", "off")
        format_pflash1.set_param("file", protocol_pflash1.get_qid())
        devs.extend([protocol_pflash1, format_pflash1])
        # machine_params["pflash1"] = format_pflash1.params["node-name"]

        # TODO:
        # else:
        #     devs.append(qdevices.QDrive(pflash1, use_device=False))
        #     devs[-1].set_param("if", "pflash")
        #     devs[-1].set_param("format", pflash_vars_format)
        #     devs[-1].set_param("file", pflash_vars_path)

    return devs
