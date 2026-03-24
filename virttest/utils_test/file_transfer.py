"""File transfer utilities for host-guest data transfer tests.

Moved from virttest.utils_test.__init__ to reduce file size.
All functions remain importable from virttest.utils_test for
backward compatibility.
"""

from __future__ import division

import logging
import os
import re
import tempfile

import aexpect
from avocado.core import exceptions
from avocado.utils import crypto, process
from six.moves import xrange

from virttest import (
    data_dir,
    error_context,
    qemu_virtio_port,
    utils_disk,
    utils_misc,
)

LOG = logging.getLogger("avocado." + __name__)


@error_context.context_aware
def run_file_transfer(test, params, env):
    """Transfer a file back and forth between host and guest.

    1) Boot up a VM.
    2) Create a large file by dd on host.
    3) Copy this file from host to guest.
    4) Copy this file from guest to host.
    5) Check if file transfers ended good.

    :param test: QEMU test object.
    :param params: Dictionary with the test parameters.
    :param env: Dictionary with test environment.
    """
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    login_timeout = int(params.get("login_timeout", 360))
    session = vm.wait_for_login(timeout=login_timeout)
    error_context.context("Login to guest", LOG.info)
    transfer_timeout = int(params.get("transfer_timeout", 1000))
    clean_cmd = params.get("clean_cmd", "rm -f")
    filesize = int(params.get("filesize", 4000))
    count = int(filesize / 10) or 1
    host_path = tempfile.mktemp(prefix="tmp-", dir=data_dir.get_tmp_dir())
    if params.get("os_type") != "windows":
        tmp_dir = params.get("tmp_dir", "/var/tmp")
        guest_path = tempfile.mktemp(prefix="transferred-", dir=tmp_dir)
    else:
        tmp_dir = params.get("tmp_dir", "c:\\")
        guest_path = "\\".join([tmp_dir, utils_misc.generate_random_string(8)])
        guest_path = "\\".join(filter(None, re.split(r"\\+", guest_path)))
    utils_disk.check_free_disk(session, tmp_dir, filesize)

    cmd = f"dd if=/dev/zero of={host_path} bs=10M count={count}"
    try:
        error_context.context(f"Creating {filesize}MB file on host", LOG.info)
        process.run(cmd)
        original_md5 = crypto.hash_file(host_path, algorithm="md5")
        error_context.context(
            f"Transferring file host -> guest, timeout: {transfer_timeout}s",
            LOG.info,
        )
        vm.copy_files_to(
            host_path, guest_path, timeout=transfer_timeout, filesize=filesize
        )

        error_context.context(
            f"Transferring file guest -> host, timeout: {transfer_timeout}s",
            LOG.info,
        )
        vm.copy_files_from(
            guest_path, host_path, timeout=transfer_timeout, filesize=filesize
        )
        current_md5 = crypto.hash_file(host_path, algorithm="md5")

        error_context.context(
            "Compare md5sum between original file and " "transferred file", LOG.info
        )
        if original_md5 != current_md5:
            raise exceptions.TestFail(
                "File changed after transfer host -> guest " "and guest -> host"
            )
    finally:
        try:
            os.remove(host_path)
        except OSError as detail:
            LOG.warning("Could not remove temp files in host: '%s'", detail)
        LOG.info("Cleaning temp file on guest")
        try:
            session.cmd(f"{clean_cmd} {guest_path}")
        except aexpect.ShellError as detail:
            LOG.warning("Could not remove temp files in guest: '%s'", detail)
        finally:
            session.close()


@error_context.context_aware
def run_virtio_serial_file_transfer(
    test, params, env, port_name=None, sender="guest", md5_check=True
):
    """Transfer file between host and guest through virtio serial.

    :param test: QEMU test object.
    :param params: Dictionary with the test parameters.
    :param env: Dictionary with test environment.
    :param port_name: VM's serial port name used to transfer data.
    :param sender: Who is data sender. guest, host or both.
    :param md5_check: Check md5 or not.
    """

    def get_virtio_port_host_file(vm, port_name):
        """Returns separated virtserialports.

        :param vm: VM object
        :param port_name: name of the virtio serial port
        :return: All virtserialports
        """
        for port in vm.virtio_ports:
            if isinstance(port, qemu_virtio_port.VirtioSerial):
                if port.name == port_name:
                    return port.hostfile

    def run_host_cmd(host_cmd, timeout=720):
        return process.run(host_cmd, shell=True, timeout=timeout).stdout_text

    def transfer_data(session, host_cmd, guest_cmd, n_time, timeout, md5_check, action):
        for num in xrange(n_time):
            md5_host = "1"
            md5_guest = "2"
            LOG.info("Data transfer repeat %s/%s.", num + 1, n_time)
            try:
                args = (host_cmd, timeout)
                host_thread = utils_misc.InterruptedThread(run_host_cmd, args)
                host_thread.start()
                g_output = session.cmd_output(guest_cmd, timeout=timeout)
                if action == "both":
                    if "Md5MissMatch" in g_output:
                        err = "Data lost during file transfer. Md5 miss match."
                        err += f" Script output:\n{g_output}"
                        if md5_check:
                            raise exceptions.TestFail(err)
                        else:
                            LOG.warning(err)
                else:
                    md5_re = r"md5_sum = (\w{32})"
                    try:
                        md5_guest = re.findall(md5_re, g_output)[0]
                    except Exception:
                        err = "Fail to get md5, script may fail."
                        err += f" Script output:\n{g_output}"
                        raise exceptions.TestError(err)
            finally:
                if host_thread:
                    output = ""
                    output = host_thread.join(10)
                    if action == "both":
                        if "Md5MissMatch" in output:
                            err = "Data lost during file transfer. Md5 miss "
                            err += f"match. Script output:\n{output}"
                            if md5_check:
                                raise exceptions.TestFail(err)
                            else:
                                LOG.warning(err)
                    else:
                        md5_re = r"md5_sum = (\w{32})"
                        try:
                            md5_host = re.findall(md5_re, output)[0]
                        except Exception:
                            err = "Fail to get md5, script may fail."
                            err += f" Script output:\n{output}"
                            raise exceptions.TestError(err)
                if action != "both" and md5_host != md5_guest:
                    err = "Data lost during file transfer. Md5 miss match."
                    err += f" Guest script output:\n {g_output}"
                    err += f" Host script output:\n{output}"
                    if md5_check:
                        raise exceptions.TestFail(err)
                    else:
                        LOG.warning(err)

    env["serial_file_transfer_start"] = False
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    timeout = int(params.get("login_timeout", 360))
    session = vm.wait_for_login(timeout=timeout)

    if not port_name:
        port_name = params["file_transfer_serial_port"]
    guest_scripts = params["guest_scripts"]
    guest_path = params.get("guest_script_folder", "C:\\")
    error_context.context("Copy test scripts to guest.", LOG.info)
    for script in guest_scripts.split(";"):
        link = os.path.join(data_dir.get_root_dir(), "shared", "deps", "serial", script)
        vm.copy_files_to(link, guest_path, timeout=60)
    host_device = get_virtio_port_host_file(vm, port_name)

    dir_name = data_dir.get_tmp_dir()
    transfer_timeout = int(params.get("transfer_timeout", 720))
    tmp_dir = params.get("tmp_dir", "/var/tmp/")
    filesize = int(params.get("filesize", 10))
    count = int(filesize)

    host_data_file = os.path.join(
        dir_name, f"tmp-{utils_misc.generate_random_string(8)}"
    )
    guest_data_file = os.path.join(
        tmp_dir, f"tmp-{utils_misc.generate_random_string(8)}"
    )

    if sender == "host" or sender == "both":
        cmd = f"dd if=/dev/zero of={host_data_file} bs=1M count={count}"
        error_context.context(f"Creating {filesize}MB file on host", LOG.info)
        process.run(cmd)
    else:
        guest_file_create_cmd = "dd if=/dev/zero of=%s bs=1M count=%d"
        guest_file_create_cmd = params.get(
            "guest_file_create_cmd", guest_file_create_cmd
        )
        cmd = guest_file_create_cmd % (guest_data_file, count)
        error_context.context(f"Creating {filesize}MB file on host", LOG.info)
        session.cmd(cmd, timeout=600)

    if sender == "host":
        action = "send"
        guest_action = "receive"
        txt = "Transfer data from host to guest"
    elif sender == "guest":
        action = "receive"
        guest_action = "send"
        txt = "Transfer data from guest to host"
    else:
        action = "both"
        guest_action = "both"
        txt = "Transfer data between guest and host"

    host_script = params.get("host_script", "serial_host_send_receive.py")
    host_script = os.path.join(
        data_dir.get_root_dir(), "shared", "deps", "serial", host_script
    )
    host_cmd = (f"`command -v python python3 | head -1` {host_script}"
                f" -s {host_device} -f {host_data_file} -a {action}")
    guest_script = params.get("guest_script", "VirtIoChannel_guest_send_receive.py")
    guest_script = os.path.join(guest_path, guest_script)

    guest_cmd = (f"`command -v python python3 | head -1` {guest_script}"
                 f" -d {port_name} -f {guest_data_file} -a {guest_action}")
    n_time = int(params.get("repeat_times", 1))
    txt += f" for {n_time} times"
    try:
        env["serial_file_transfer_start"] = True
        transfer_data(
            session, host_cmd, guest_cmd, n_time, transfer_timeout, md5_check, action
        )
    finally:
        env["serial_file_transfer_start"] = False
    if session:
        session.close()
