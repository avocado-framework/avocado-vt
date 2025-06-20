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


import logging
import os

from avocado_vt.agent.core import data_dir as core_data_dir
from virttest import data_dir, utils_logfile
from virttest.qemu_devices import qdevices
from virttest.qemu_devices.utils import set_cmdline_format_by_cfg
from virttest.utils_params import Params

import aexpect

LOG = logging.getLogger("avocado.service." + __name__)


def create_tpm_devices(tpm, instance_id, format_cfg):
    def _handle_log(line):
        try:
            log_filename = os.path.join(
                core_data_dir.get_daemon_log_dir(),
                "%s_%s_swtpm_setup.log" % (instance_id, tpm_id),
            )
            utils_logfile.log_line(log_filename, line)
        except Exception as e:
            LOG.warn("Can't log %s_swtpm_setup output: %s.", tpm_id, e)

    def _emulator_setup(binary, extra_options=None):
        setup_cmd = binary
        if tpm_version in ("2.0",):
            setup_cmd += " --tpm2"

        tpm_path = os.path.join(swtpm_dir, "%s_state" % tpm_id)
        if not os.path.exists(tpm_path):
            os.makedirs(tpm_path)
        setup_cmd += " --tpm-state %s" % tpm_path

        setup_cmd += (
            " --createek --create-ek-cert" " --create-platform-cert" " --lock-nvram"
        )
        tpm_overwrite = tpm_props.get("overwrite")
        overwrite_option = " --overwrite" if tpm_overwrite else " --not-overwrite"
        setup_cmd += overwrite_option

        if extra_options:
            setup_cmd += extra_options

        LOG.info(
            "<Instance: %s> Running TPM emulator setup command: %s",
            instance_id,
            setup_cmd,
        )
        _process = aexpect.run_bg(setup_cmd, None, _handle_log, auto_close=False)
        status_ending = "Ending vTPM manufacturing"
        _process.read_until_any_line_matches(status_ending, timeout=5)
        return tpm_path

    devs = []
    tpm_type = tpm.get("type")
    tpm_id = tpm.get("id")
    tpm_props = tpm.get("props")
    tpm_setup_bin = tpm_props.get("setup_bin")
    tpm_setup_bin_extra_options = tpm_props.get("setup_bin_extra_options")
    tpm_bin = tpm_props.get("bin")
    tpm_version = tpm_props.get("version")
    tpm_bin_extra_options = tpm_props.get("bin_extra_options")

    swtpm_dir = os.path.join(data_dir.get_data_dir(), "swtpm")

    if tpm_type == "emulator":
        sock_path = os.path.join(swtpm_dir, tpm_id + "_swtpm.sock")

        storage_path = _emulator_setup(tpm_setup_bin, tpm_setup_bin_extra_options)
        swtpmdev = qdevices.QSwtpmDev(
            tpm_id,
            tpm_bin,
            sock_path,
            storage_path,
            tpm_version,
            tpm_bin_extra_options,
        )
        devs.append(swtpmdev)

        char_params = Params()
        char_params["backend"] = "socket"
        char_params["id"] = "char_%s" % swtpmdev.get_qid()
        sock_bus = {"busid": sock_path}
        char = qdevices.CharDevice(char_params, parent_bus=sock_bus)
        char.set_aid(swtpmdev.get_aid())
        devs.append(char)
        tpm_params = {"chardev": char.get_qid()}
        tpm_id = swtpmdev.get_qid()
    elif tpm_type == "passthrough":
        tpm_params = {"path": tpm_props["path"]}
    else:
        raise ValueError("Unsupported TPM backend type.")

    tpm_params["id"] = "%s_%s" % (tpm_type, tpm_id)
    tpm_params["backend"] = tpm_type
    tpm_dev = qdevices.QCustomDevice("tpmdev", tpm_params, tpm_id, backend="backend")
    devs.append(tpm_dev)

    tpm_model = tpm.get("model")

    tpm_model_params = {
        "id": "%s_%s" % (tpm_model.get("type"), tpm_id),
        "tpmdev": tpm_dev.get_qid(),
    }
    tpm_model_params.update(tpm_model.get("props"))

    tpm_model_dev = qdevices.QDevice(tpm_model.get("type"), tpm_model_params)
    tpm_model_dev.set_aid(tpm_id)
    devs.append(tpm_model_dev)

    for dev in devs:
        set_cmdline_format_by_cfg(dev, format_cfg, "tpm")

    return devs
