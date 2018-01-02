"""
High-level virt test utility functions.

This module is meant to reduce code size by performing common test procedures.
Generally, code here should look like test code.

More specifically:
    - Functions in this module should raise exceptions if things go wrong
    - Functions in this module typically use functions and classes from
      lower-level modules (e.g. utils_misc, aexpect).
    - Functions in this module should not be used by lower-level modules.
    - Functions in this module should be used in the right context.
      For example, a function should not be used where it may display
      misleading or inaccurate info or debug messages.

:copyright: 2008-2013 Red Hat Inc.
"""

import commands
import glob
import imp
import locale
import logging
import os
import re
import signal
import tempfile
import threading
import time
import subprocess

import aexpect
from avocado.core import exceptions
from avocado.utils import process
from avocado.utils import aurl
from avocado.utils import download
from avocado.utils import crypto
from avocado.utils import path


# Import from the top level virttest namespace
from .. import asset
from .. import bootstrap
from .. import data_dir
from .. import error_context
from .. import qemu_virtio_port
from .. import remote
from .. import scan_autotest_results
from .. import storage
from .. import utils_misc
from .. import utils_net
from .. import virt_vm
from ..staging import utils_memory

# Get back to importing submodules
# This is essential for accessing these submodules directly from
# utils_test namespace like:
# >>> from virttest import utils_test
# >>> utils_test.qemu.SomeClass()
#
# pylint: disable=unused-import
from . import qemu
from . import libvirt
from . import libguestfs


# This is so that other tests won't break when importing the names
# 'ping' and 'raw_ping' from this namespace
ping = utils_net.ping
raw_ping = utils_net.raw_ping


@error_context.context_aware
def update_boot_option(vm, args_removed=None, args_added=None,
                       need_reboot=True):
    """
    Update guest default kernel option.

    :param vm: The VM object.
    :param args_removed: Kernel options want to remove.
    :param args_added: Kernel options want to add.
    :param need_reboot: Whether need reboot VM or not.
    :raise exceptions.TestError: Raised if fail to update guest kernel cmdline.

    """
    if vm.params.get("os_type") == 'windows':
        # this function is only for linux, if we need to change
        # windows guest's boot option, we can use a function like:
        # update_win_bootloader(args_removed, args_added, reboot)
        # (this function is not implement.)
        # here we just:
        return

    login_timeout = int(vm.params.get("login_timeout"))
    session = vm.wait_for_login(timeout=login_timeout)

    msg = "Update guest kernel option. "
    cmd = "grubby --update-kernel=`grubby --default-kernel` "
    if args_removed is not None:
        msg += " remove args: %s" % args_removed
        cmd += '--remove-args="%s" ' % args_removed
    if args_added is not None:
        msg += " add args: %s" % args_added
        cmd += '--args="%s"' % args_added
    error_context.context(msg, logging.info)
    status, output = session.cmd_status_output(cmd)
    if status != 0:
        logging.error(output)
        raise exceptions.TestError("Fail to modify guest kernel option")

    if need_reboot:
        error_context.context("Rebooting guest ...", logging.info)
        session = vm.reboot(session=session, timeout=login_timeout)
    cmdline = session.cmd("cat /proc/cmdline", timeout=60)
    if args_removed and args_removed in cmdline:
        logging.error(output)
        err = "Fail to remove guest kernel option %s" % args_removed
        raise exceptions.TestError(err)
    if args_added and args_added not in cmdline:
        logging.error(output)
        err = "Fail to add guest kernel option %s" % args_added
        raise exceptions.TestError(err)


def stop_windows_service(session, service, timeout=120):
    """
    Stop a Windows service using sc.
    If the service is already stopped or is not installed, do nothing.

    :param service: The name of the service
    :param timeout: Time duration to wait for service to stop
    :raise exceptions.TestError: Raised if the service can't be stopped
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        o = session.cmd_output("sc stop %s" % service, timeout=60)
        # FAILED 1060 means the service isn't installed.
        # FAILED 1062 means the service hasn't been started.
        if re.search(r"\bFAILED (1060|1062)\b", o, re.I):
            break
        time.sleep(1)
    else:
        raise exceptions.TestError("Could not stop service '%s'" % service)


def start_windows_service(session, service, timeout=120):
    """
    Start a Windows service using sc.
    If the service is already running, do nothing.
    If the service isn't installed, fail.

    :param service: The name of the service
    :param timeout: Time duration to wait for service to start
    :raise exceptions.TestError: Raised if the service can't be started
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        o = session.cmd_output("sc start %s" % service, timeout=60)
        # FAILED 1060 means the service isn't installed.
        if re.search(r"\bFAILED 1060\b", o, re.I):
            raise exceptions.TestError("Could not start service '%s' "
                                       "(service not installed)" % service)
        # FAILED 1056 means the service is already running.
        if re.search(r"\bFAILED 1056\b", o, re.I):
            break
        time.sleep(1)
    else:
        raise exceptions.TestError("Could not start service '%s'" % service)


def get_windows_file_abs_path(session, filename, extension="exe", tmout=240):
    """
    return file abs path "drive+path" by "wmic datafile"
    """
    cmd_tmp = "wmic datafile where \"Filename='%s' and "
    cmd_tmp += "extension='%s'\" get drive^,path"
    cmd = cmd_tmp % (filename, extension)
    info = session.cmd_output(cmd, timeout=tmout).strip()
    drive_path = re.search(r'(\w):\s+(\S+)', info, re.M)
    if not drive_path:
        raise exceptions.TestError("Not found file %s.%s in your guest"
                                   % (filename, extension))
    return ":".join(drive_path.groups())


def get_windows_disk_drive(session, filename, extension="exe", tmout=240):
    """
    Get the windows disk drive number
    """
    return get_windows_file_abs_path(session, filename,
                                     extension).split(":")[0]


def get_time(session, time_command, time_filter_re, time_format):
    """
    Return the host time and guest time.  If the guest time cannot be fetched
    a TestError exception is raised.

    Note that the shell session should be ready to receive commands
    (i.e. should "display" a command prompt and should be done with all
    previous commands).

    :param session: A shell session.
    :param time_command: Command to issue to get the current guest time.
    :param time_filter_re: Regex filter to apply on the output of
            time_command in order to get the current time.
    :param time_format: Format string to pass to time.strptime() with the
            result of the regex filter.
    :return: A tuple containing the host time and guest time.
    """
    if re.findall("ntpdate|w32tm", time_command):
        output = session.cmd_output_safe(time_command)
        if re.match('ntpdate', time_command):
            try:
                offset = re.findall('offset (.*) sec', output)[0]
            except IndexError:
                msg = "Fail to get guest time offset. Command "
                msg += "'%s', output: %s" % (time_command, output)
                raise exceptions.TestError(msg)
            try:
                host_main, host_mantissa = re.findall(
                    time_filter_re, output)[0]
                host_time = (time.mktime(time.strptime(host_main, time_format)) +
                             float("0.%s" % host_mantissa))
            except Exception:
                msg = "Fail to get host time. Command '%s', " % time_command
                msg += "output: %s" % output
                raise exceptions.TestError(msg)
            guest_time = host_time - float(offset)
        else:
            try:
                guest_time = re.findall(time_filter_re, output)[0]
            except IndexError:
                msg = "Fail to get guest time. Command '%s', " % time_command
                msg += "output: %s" % output
                raise exceptions.TestError(msg)
            try:
                offset = re.findall("o:(.*)s", output)[0]
            except IndexError:
                msg = "Fail to get guest time offset. Command "
                msg += "'%s', output: %s" % (time_command, output)
                raise exceptions.TestError(msg)
            if re.search('PM|AM', guest_time):
                hour = re.findall('\d+ (\d+):', guest_time)[0]
                fix = 12 if re.search('PM', guest_time) else 0
                hour = str(int(hour) % 12 + fix)
                guest_time = re.sub('\s\d+:', " %s:" % hour,
                                    guest_time)[:-3]
            else:
                guest_time = guest_time[:-3]
            guest_time = time.mktime(time.strptime(guest_time, time_format))
            host_time = guest_time + float(offset)
    elif re.findall("hwclock", time_command):
        loc = locale.getlocale(locale.LC_TIME)
        # Get and parse host time
        host_time_out = process.run(time_command).stdout
        diff = host_time_out.split()[-2]
        host_time_out = " ".join(host_time_out.split()[:-2])
        try:
            try:
                locale.setlocale(locale.LC_TIME, "C")
                host_time = time.mktime(
                    time.strptime(host_time_out, time_format))
                host_time += float(diff)
            except Exception, err:
                logging.debug("(time_format, time_string): (%s, %s)",
                              time_format, host_time_out)
                raise err
        finally:
            locale.setlocale(locale.LC_TIME, loc)

        output = session.cmd_output_safe(time_command)

        # Get and parse guest time
        try:
            str_time = re.findall(time_filter_re, output)[0]
            diff = str_time.split()[-2]
            str_time = " ".join(str_time.split()[:-2])
        except IndexError:
            logging.debug("The time string from guest is:\n%s", str_time)
            raise exceptions.TestError(
                "The time string from guest is unexpected.")
        except Exception, err:
            logging.debug("(time_filter_re, time_string): (%s, %s)",
                          time_filter_re, str_time)
            raise err

        guest_time = None
        try:
            try:
                locale.setlocale(locale.LC_TIME, "C")
                guest_time = time.mktime(time.strptime(str_time, time_format))
                guest_time += float(diff)
            except Exception, err:
                logging.debug("(time_format, time_string): (%s, %s)",
                              time_format, str_time)
                raise err
        finally:
            locale.setlocale(locale.LC_TIME, loc)
    else:
        host_time = time.time()
        output = session.cmd_output_safe(time_command).strip()
        num = 0.0
        reo = None

        try:
            reo = re.findall(time_filter_re, output)
            str_time = reo[0]
            if len(reo) > 1:
                num = float(reo[1])
        except IndexError:
            logging.debug("The time string from guest is:\n%s", output)
            raise exceptions.TestError(
                "The time string from guest is unexpected.")
        except ValueError, err:
            logging.debug("Couldn't parse float time offset from %s" % reo)
        except Exception, err:
            logging.debug("(time_filter_re, time_string): (%s, %s)",
                          time_filter_re, output)
            raise err

        guest_time = time.mktime(time.strptime(str_time, time_format)) + num

    return (host_time, guest_time)


def get_memory_info(lvms):
    """
    Get memory information from host and guests in format:
    Host: memfree = XXXM; Guests memsh = {XXX,XXX,...}

    :params lvms: List of VM objects
    :return: String with memory info report
    """
    if not isinstance(lvms, list):
        raise exceptions.TestError(
            "Invalid list passed to get_stat: %s " % lvms)

    try:
        meminfo = "Host: memfree = "
        meminfo += str(int(utils_memory.read_from_meminfo('MemFree')) / 1024) + "M; "
        meminfo += "swapfree = "
        mf = int(utils_memory.read_from_meminfo("SwapFree")) / 1024
        meminfo += str(mf) + "M; "
    except Exception, e:
        raise exceptions.TestFail("Could not fetch host free memory info, "
                                  "reason: %s" % e)

    meminfo += "Guests memsh = {"
    for vm in lvms:
        shm = vm.get_shared_meminfo()
        if shm is None:
            raise exceptions.TestError("Could not get shared meminfo from "
                                       "VM %s" % vm)
        meminfo += "%dM; " % shm
    meminfo = meminfo[0:-2] + "}"

    return meminfo


@error_context.context_aware
def get_image_version(qemu_image):
    """
    Get image version of qcow2 image

    :param qemu_image: Object QemuImg

    :return: compatibility level
    """
    error_context.context("Get qcow2 image('%s') version"
                          % qemu_image.image_filename, logging.info)
    info_out = qemu_image.info()
    compat = re.search(r'compat: +(.*)', info_out, re.M)
    if compat:
        return compat.group(1)
    return '0.10'


@error_context.context_aware
def update_qcow2_image_version(qemu_image, ver_from, ver_to):
    """
    Update qcow2 image version.

    :param qemu_image: Object QemuImg
    :param ver_from: Original version of qcow2 image. Valid values: '0.10'
                 and '1.1'
    :param ver_to: Version which is expected to be set. Valid values: '0.10'
               and '1.1'
    """
    if ver_from == ver_to:
        return None
    error_context.context("Update qcow2 image version from %s to %s"
                          % (ver_from, ver_to), logging.info)
    qemu_image.params.update({"amend_compat": "%s" % ver_to})
    qemu_image.amend(qemu_image.params)


@error_context.context_aware
def run_image_copy(test, params, env):
    """
    Copy guest images from nfs server.
    1) Mount the NFS share directory
    2) Check the existence of source image
    3) If it exists, copy the image from NFS

    Note about 'source_image_name' parameter.  'image_copy' test is used for
    copying existing/pristine image for usage in further tests.
    'source_image_name' parameter gives you ability to copy one image to
    different image_copy(_vm_suffix_name) = image.  This parameter could be
    helpful in case of two and more simultaneously running vms: vms = vm1 vm2

    :param test: kvm test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment.
    """
    vm = env.get_vm(params["main_vm"])
    if vm is not None:
        vm.destroy()

    src = params.get('images_good')
    asset_name = '%s' % (os.path.split(params['image_name'])[1])
    # Define special image to be taken as a source.
    source_image_name = params.get('source_image_name')
    if source_image_name:
        logging.info('Using image as source image: %s', source_image_name)
        asset_name = '%s' % (os.path.split(source_image_name)[1])
    image = '%s.%s' % (params['image_name'], params['image_format'])
    dst_path = storage.get_image_filename(params, data_dir.get_data_dir())
    image_dir = os.path.dirname(dst_path)
    if params.get("rename_error_image", "no") == "yes":
        error_image = os.path.basename(params['image_name']) + "-error"
        error_image += '.' + params['image_format']
        error_dst_path = os.path.join(image_dir, error_image)
        mv_cmd = "/bin/mv %s %s" % (dst_path, error_dst_path)
        process.system(mv_cmd, timeout=360, ignore_status=True)

    if src:
        mount_dest_dir = params.get('dst_dir', '/mnt/images')
        if not os.path.exists(mount_dest_dir):
            try:
                os.makedirs(mount_dest_dir)
            except OSError, err:
                logging.warning('mkdir %s error:\n%s', mount_dest_dir, err)

        if not os.path.exists(mount_dest_dir):
            raise exceptions.TestError('Failed to create NFS share dir %s' %
                                       mount_dest_dir)

        error_context.context("Mount the NFS share directory")
        if not utils_misc.mount(src, mount_dest_dir, 'nfs', 'ro'):
            raise exceptions.TestError('Could not mount NFS share %s to %s' %
                                       (src, mount_dest_dir))

        error_context.context("Check the existence of source image")
        src_path = '%s/%s.%s' % (mount_dest_dir, asset_name,
                                 params['image_format'])
        asset_info = asset.get_file_asset(asset_name, src_path, dst_path)
        if asset_info is None:
            raise exceptions.TestError('Could not find %s' % image)
    else:
        asset_info = asset.get_asset_info(asset_name)

    # Do not force extraction if integrity information is available
    if asset_info['sha1_url']:
        force = params.get("force_copy", "no") == "yes"
    else:
        force = params.get("force_copy", "yes") == "yes"

    try:
        error_context.context("Copy image '%s'" % image, logging.info)
        if aurl.is_url(asset_info['url']):
            asset.download_file(asset_info, interactive=False,
                                force=force)
        else:
            download.get_file(asset_info['url'], asset_info['destination'])

    finally:
        sub_type = params.get("sub_type")
        if sub_type:
            error_context.context("Run sub test '%s'" % sub_type, logging.info)
            params['image_name'] += "-error"
            params['boot_once'] = "c"
            vm.create(params=params)
            run_virt_sub_test(test, params, env, params.get("sub_type"))


@error_context.context_aware
def run_file_transfer(test, params, env):
    """
    Transfer a file back and forth between host and guest.

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
    error_context.context("Login to guest", logging.info)
    transfer_timeout = int(params.get("transfer_timeout", 1000))
    clean_cmd = params.get("clean_cmd", "rm -f")
    filesize = int(params.get("filesize", 4000))
    count = int(filesize / 10) or 1
    host_path = tempfile.mktemp(prefix="tmp-", dir=test.tmpdir)
    if params.get("os_type") != 'windows':
        tmp_dir = params.get("tmp_dir", "/var/tmp")
        guest_path = tempfile.mktemp(prefix="transferred-", dir=tmp_dir)
    else:
        tmp_dir = params.get("tmp_dir", "c:\\")
        guest_path = "\\".join([tmp_dir, utils_misc.generate_random_string(8)])
        guest_path = "\\".join(filter(None, re.split(r"\\+", guest_path)))
    cmd = "dd if=/dev/zero of=%s bs=10M count=%d" % (host_path, count)
    try:
        error_context.context(
            "Creating %dMB file on host" % filesize, logging.info)
        process.run(cmd)
        original_md5 = crypto.hash_file(host_path, algorithm="md5")
        error_context.context("Transferring file host -> guest, "
                              "timeout: %ss" % transfer_timeout, logging.info)
        vm.copy_files_to(
            host_path,
            guest_path,
            timeout=transfer_timeout,
            filesize=filesize)

        error_context.context("Transferring file guest -> host, "
                              "timeout: %ss" % transfer_timeout, logging.info)
        vm.copy_files_from(
            guest_path,
            host_path,
            timeout=transfer_timeout,
            filesize=filesize)
        current_md5 = crypto.hash_file(host_path, algorithm="md5")

        error_context.context("Compare md5sum between original file and "
                              "transferred file", logging.info)
        if original_md5 != current_md5:
            raise exceptions.TestFail("File changed after transfer host -> guest "
                                      "and guest -> host")
    finally:
        try:
            os.remove(host_path)
        except OSError, detail:
            logging.warn("Could not remove temp files in host: '%s'", detail)
        logging.info('Cleaning temp file on guest')
        try:
            session.cmd("%s %s" % (clean_cmd, guest_path))
        except aexpect.ShellError, detail:
            logging.warn("Could not remove temp files in guest: '%s'", detail)
        finally:
            session.close()


@error_context.context_aware
def run_virtio_serial_file_transfer(test, params, env, port_name=None,
                                    sender="guest", md5_check=True):
    """
    Transfer file between host and guest through virtio serial.

    :param test: QEMU test object.
    :param params: Dictionary with the test parameters.
    :param env: Dictionary with test environment.
    :param port_name: VM's serial port name used to transfer data.
    :param sender: Who is data sender. guest, host or both.
    :param md5_check: Check md5 or not.
    """
    def get_virtio_port_host_file(vm, port_name):
        """
        Returns separated virtserialports
        :param vm: VM object
        :return: All virtserialports
        """
        for port in vm.virtio_ports:
            if isinstance(port, qemu_virtio_port.VirtioSerial):
                if port.name == port_name:
                    return port.hostfile

    def run_host_cmd(host_cmd, timeout=720):
        return process.system_output(host_cmd, timeout=timeout)

    def transfer_data(session, host_cmd, guest_cmd, n_time, timeout,
                      md5_check, action):
        for num in xrange(n_time):
            md5_host = "1"
            md5_guest = "2"
            logging.info("Data transfer repeat %s/%s." % (num + 1, n_time))
            try:
                args = (host_cmd, timeout)
                host_thread = utils_misc.InterruptedThread(run_host_cmd, args)
                host_thread.start()
                g_output = session.cmd_output(guest_cmd, timeout=timeout)
                if action == "both":
                    if "Md5MissMatch" in g_output:
                        err = "Data lost during file transfer. Md5 miss match."
                        err += " Script output:\n%s" % g_output
                        if md5_check:
                            raise exceptions.TestFail(err)
                        else:
                            logging.warn(err)
                else:
                    md5_re = "md5_sum = (\w{32})"
                    try:
                        md5_guest = re.findall(md5_re, g_output)[0]
                    except Exception:
                        err = "Fail to get md5, script may fail."
                        err += " Script output:\n%s" % g_output
                        raise exceptions.TestError(err)
            finally:
                if host_thread:
                    output = ""
                    output = host_thread.join(10)
                    if action == "both":
                        if "Md5MissMatch" in output:
                            err = "Data lost during file transfer. Md5 miss "
                            err += "match. Script output:\n%s" % output
                            if md5_check:
                                raise exceptions.TestFail(err)
                            else:
                                logging.warn(err)
                    else:
                        md5_re = "md5_sum = (\w{32})"
                        try:
                            md5_host = re.findall(md5_re, output)[0]
                        except Exception:
                            err = "Fail to get md5, script may fail."
                            err += " Script output:\n%s" % output
                            raise exceptions.TestError(err)
                if action != "both" and md5_host != md5_guest:
                    err = "Data lost during file transfer. Md5 miss match."
                    err += " Guest script output:\n %s" % g_output
                    err += " Host script output:\n%s" % output
                    if md5_check:
                        raise exceptions.TestFail(err)
                    else:
                        logging.warn(err)

    env["serial_file_transfer_start"] = False
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    timeout = int(params.get("login_timeout", 360))
    session = vm.wait_for_login(timeout=timeout)

    if not port_name:
        port_name = params["file_transfer_serial_port"]
    guest_scripts = params["guest_scripts"]
    guest_path = params.get("guest_script_folder", "C:\\")
    error_context.context("Copy test scripts to guest.", logging.info)
    for script in guest_scripts.split(";"):
        link = os.path.join(data_dir.get_root_dir(), "shared", "deps",
                            "serial", script)
        vm.copy_files_to(link, guest_path, timeout=60)
    host_device = get_virtio_port_host_file(vm, port_name)

    dir_name = test.tmpdir
    transfer_timeout = int(params.get("transfer_timeout", 720))
    tmp_dir = params.get("tmp_dir", data_dir.get_tmp_dir())
    filesize = int(params.get("filesize", 10))
    count = int(filesize)

    host_data_file = os.path.join(dir_name,
                                  "tmp-%s" % utils_misc.generate_random_string(8))
    guest_data_file = os.path.join(tmp_dir,
                                   "tmp-%s" % utils_misc.generate_random_string(8))

    if sender == "host" or sender == "both":
        cmd = "dd if=/dev/zero of=%s bs=1M count=%d" % (host_data_file, count)
        error_context.context(
            "Creating %dMB file on host" % filesize, logging.info)
        process.run(cmd)
    else:
        guest_file_create_cmd = "dd if=/dev/zero of=%s bs=1M count=%d"
        guest_file_create_cmd = params.get("guest_file_create_cmd",
                                           guest_file_create_cmd)
        cmd = guest_file_create_cmd % (guest_data_file, count)
        error_context.context(
            "Creating %dMB file on host" % filesize, logging.info)
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
        txt = "Transfer data betwwen guest and host"

    host_script = params.get("host_script", "serial_host_send_receive.py")
    host_script = os.path.join(data_dir.get_root_dir(), "shared", "deps",
                               "serial", host_script)
    host_cmd = "python %s -s %s -f %s -a %s" % (host_script, host_device,
                                                host_data_file, action)
    guest_script = params.get("guest_script",
                              "VirtIoChannel_guest_send_receive.py")
    guest_script = os.path.join(guest_path, guest_script)

    guest_cmd = "python %s -d %s -f %s -a %s" % (guest_script, port_name,
                                                 guest_data_file, guest_action)
    n_time = int(params.get("repeat_times", 1))
    txt += " for %s times" % n_time
    try:
        env["serial_file_transfer_start"] = True
        transfer_data(session, host_cmd, guest_cmd, n_time, transfer_timeout,
                      md5_check, action)
    finally:
        env["serial_file_transfer_start"] = False
    if session:
        session.close()


def run_avocado(vm, params, test, testlist=[], timeout=3600,
                testrepo="https://github.com/avocado-framework-tests/avocado-misc-tests.git",
                installtype="pip", reinstall=False, add_args=None, ignore_result=True):
    """
    Function to run avocado tests inside guest

    :param vm: VM object
    :param params: VM param
    :param test: test object
    :param testlist: testlist as list of tuples like (testcase, muxfile)
    :param timeout: test timeout
    :param testrepo: test repository default is avocado-misc-tests
    :param installtype: how to install avocado, supported types
                        pip, package, git
    :param reinstall: flag to reinstall incase of avocado present inside guest
    :param add_args: additional arguments to be passed to the avocado cmdline
    :param ignore_result: True or False
    :return: Bool result status
    """
    plugins = {'pip': ['avocado-framework-plugin-varianter-yaml-to-mux', 'avocado-framework-plugin-result-html'],
               'package': [],
               'git': ['varianter_yaml_to_mux', 'html']}
    prerequisites = ['python', 'git']

    def env_check():
        """
        Check prerequisites
        """
        # TODO: Try installing the prerequisites
        err_msg = "Following packages not availale: "
        check = True
        for item in prerequisites:
            cmd = "which %s" % item
            if session.cmd_status(cmd) > 0:
                check = False
                err_msg += "%s " % item
        if not check:
            err_msg += "\nConsider install them and rerun"
            raise exceptions.TestError(err_msg)

    def install_avocado(installtype="pip"):
        """
        Install avocado
        """
        logging.debug("Installing avocado")
        status = 0
        if (session.cmd_status("which avocado") == 0) and not reinstall:
            return True
        if "pip" in installtype:
            cmd = "python -m pip --version || python -c \"import os; import sys;"
            cmd += " import urllib;f = urllib.urlretrieve(\'https://bootstrap.pypa.io/get-pip.py\')[0]; "
            cmd += "os.system(\'%s %s\' % (sys.executable, f))\""
            if session.cmd_status(cmd) > 0:
                logging.error("pip installation failed")
                return False
            cmd = "pip install avocado-framework"
            if session.cmd_status(cmd) > 0:
                logging.error("Avocado pip installation failed")
                return False
            for plugin in plugins[installtype]:
                cmd = "pip install %s" % plugin
                if session.cmd_status(cmd) > 0:
                    logging.error("Avocado plugin %s pip installation failed", plugin)
                    return False
        elif "package" in installtype:
            raise NotImplementedError
        elif "git" in installtype:
            test_path = params.get("vm_test_path", "/var/tmp/avocado/")
            cmd = "git clone https://github.com/avocado-framework/avocado.git;"
            cmd += "cd avocado;python setup.py install"
            if session.cmd_status(cmd) > 0:
                logging.error("Avocado git installation failed")
                return False
            for plugin in plugins[installtype]:
                cmd = "[ -d optional_plugins/%s ] && cd optional_plugins/" % plugin
                cmd += "%s && python setup.py install && cd .." % plugin
                if session.cmd_status(cmd) > 0:
                    logging.error("Avocado plugin %s git installation failed", plugin)
                    return False
        return True

    def runtest(session, testrepo, testlist, timeout, result_path, test_path):
        """
        run test
        """
        success = True

        cmd = "[ -n \"$(ls %s)\" ]" % test_path
        if session.cmd_status(cmd) > 0:
            cmd = "mkdir -p %s" % test_path
            session.cmd(cmd)

        cmd = "[ -n \"$(ls %s)\" ]" % result_path
        if session.cmd_status(cmd) > 0:
            cmd = "mkdir -p %s" % result_path
            session.cmd(cmd)

        logging.debug("Downloading Test")
        cmd = "cd %s;[ -d %s ] || git clone %s" % (test_path,
                                                   testrepo.split("/")[-1].split('.')[0],
                                                   testrepo)
        status, output = session.cmd_status_output(cmd, timeout=100)
        if status > 0:
            raise exceptions.TestError("Downloading test failed: %s" % output)
        logging.debug("Running Test")
        for test in testlist:
            mux = ""
            testcase = test[0]
            testcase = os.path.join(test_path,
                                    testrepo.split("/")[-1].split('.')[0],
                                    testcase)
            try:
                mux = test[1]
            except KeyError:
                pass
            cmd = "avocado run %s --job-results-dir %s --job-timeout %d" % (testcase, result_path, timeout)
            if mux:
                cmd += " -m %s" % mux
            if add_args:
                cmd += " %s" % add_args
            status, output = session.cmd_status_output(cmd, timeout=timeout)
            if status > 0:
                # TODO: Map test return status with error strings and print
                logging.error("Testcase: %s has failures consult "
                              "the logs for details\nstatus: "
                              "%s\nstdout: %s", testcase, status, output)
                success = False
        return success

    def get_results(test_path, result_path, session):
        """
        Copy avocado results present on the guest back to the host.
        """
        logging.debug("Trying to copy avocado results from guest")
        cmd = "[ -n \"$(ls %s)\" ]" % result_path
        if session.cmd_status(cmd) > 0:
            raise exceptions.TestError("No results folder found")
        guest_results_dir = utils_misc.get_path(test.debugdir, "guest_avocado_results")
        os.makedirs(guest_results_dir)
        logging.debug("Guest avocado test results placed under %s", guest_results_dir)
        # result info tarball to host result dir
        results_tarball = os.path.join(test_path, "results.tgz")
        compress_cmd = "cd %s && " % result_path
        compress_cmd += "tar cjvf %s ./*" % results_tarball
        compress_cmd += " --exclude=*core*"
        compress_cmd += " --exclude=*crash*"
        session.cmd(compress_cmd, timeout=600)
        vm.copy_files_from(results_tarball, guest_results_dir)
        # cleanup results dir from guest
        clean_cmd = "rm -f %s;rm -rf %s" % (results_tarball, result_path)
        session.cmd(clean_cmd, timeout=240)
        results_tarball = os.path.basename(results_tarball)
        results_tarball = os.path.join(guest_results_dir, results_tarball)
        uncompress_cmd = "tar xjvf %s -C %s" % (results_tarball,
                                                guest_results_dir)
        process.run(uncompress_cmd)
        process.run("rm -f %s" % results_tarball)

    # Run test
    try:
        session = vm.wait_for_login()
    except Exception:
        raise exceptions.TestError("Unable to get VM session, skipped to run avocado test")

    test_path = params.get("vm_test_path", "/var/tmp/avocado/")
    result_path = os.path.join(test_path, "results")
    if not install_avocado(installtype):
        exceptions.TestError("avocado installation failed, consult previous errors")
    test_status = runtest(session, testrepo, testlist, timeout, result_path, test_path)
    get_results(test_path, result_path, session)
    # Cleanup
    session.cmd("rm -rf %s" % test_path)

    if not test_status and not ignore_result:
        exceptions.TestFail("consult previous errors")
    else:
        return test_status


def run_autotest(vm, session, control_path, timeout,
                 outputdir, params, copy_only=False, control_args=None,
                 ignore_session_terminated=False):
    """
    Run an autotest control file inside a guest (linux only utility).

    :param vm: VM object.
    :param session: A shell session on the VM provided.
    :param control_path: A path to an autotest control file.
    :param timeout: Timeout under which the autotest control file must complete.
    :param outputdir: Path on host where we should copy the guest autotest
            results to.
    :param copy_only: If copy_only is True, copy the autotest to guest and
            return the command which need to run test on guest, without
            executing it.
    :param control_args: The arguments for control file.
    :param ignore_session_terminated: If set up this parameter to True we will
            ignore the session terminated during test.

    The following params is used by the migration
    :param params: Test params used in the migration test
    """
    from autotest.client.shared.settings import settings
    section_values = settings.get_section_values

    def directory_exists(remote_path):
        return session.cmd_status("test -d %s" % remote_path) == 0

    def copy_if_hash_differs(vm, local_path, remote_path):
        """
        Copy a file to a guest if it doesn't exist or if its MD5sum differs.

        :param vm: VM object.
        :param local_path: Local path.
        :param remote_path: Remote path.

        :return: remote file path
        """
        local_hash = crypto.hash_file(local_path)
        basename = os.path.basename(local_path)
        output = session.cmd_output("md5sum %s" % remote_path,
                                    timeout=int(
                                        params.get("md5sum_timeout", 240)))
        if "such file" in output:
            remote_hash = "0"
        elif output:
            remote_hash = output.split()[0]
        else:
            logging.warning("MD5 check for remote path %s did not return.",
                            remote_path)
            # Let's be a little more lenient here and see if it wasn't a
            # temporary problem
            remote_hash = "0"
        if remote_hash == local_hash:
            return None
        logging.debug("Copying %s to guest (remote hash: %s, local hash:%s)",
                      basename, remote_hash, local_hash)
        dest_dir = os.path.dirname(remote_path)
        if not directory_exists(dest_dir):
            session.cmd("mkdir -p %s" % dest_dir)
        vm.copy_files_to(local_path, remote_path)
        return remote_path

    def extract(vm, remote_path, dest_dir):
        """
        Extract the autotest .tar.bz2 file on the guest, ensuring the final
        destination path will be dest_dir.

        :param vm: VM object
        :param remote_path: Remote file path
        :param dest_dir: Destination dir for the contents
        """
        basename = os.path.basename(remote_path)
        logging.debug("Extracting %s on VM %s", basename, vm.name)
        session.cmd("rm -rf %s" % dest_dir, timeout=240)
        dirname = os.path.dirname(remote_path)
        session.cmd("cd %s" % dirname)
        session.cmd("mkdir -p %s" % os.path.dirname(dest_dir))
        has_pbzip2, pbzip2_path = session.cmd_status_output("which pbzip2")
        has_lbzip2, lbzip2_path = session.cmd_status_output("which lbzip2")
        if (has_pbzip2 == 0) and "pbzip2" in pbzip2_path:
            options = "--use-compress-program=pbzip2 -xvmf"
        elif (has_lbzip2 == 0) and "lbzip2" in lbzip2_path:
            options = "--use-compress-program=lbzip2 -xvmf"
        elif 'gzip' in session.cmd_output("file %s" % basename):
            options = "xzvf"
        else:
            options = "xvjmf"
        extract_cmd = "tar %s %s -C %s" % (options,
                                           basename,
                                           os.path.dirname(dest_dir))
        extract_cmd += " & wait ${!}"
        output = session.cmd(extract_cmd, timeout=120)
        autotest_dirname = ""
        for line in output.splitlines()[2:]:
            autotest_dirname = line.split("/")[0]
            break
        if autotest_dirname != os.path.basename(dest_dir):
            session.cmd("cd %s" % os.path.dirname(dest_dir))
            session.cmd("mv %s %s" %
                        (autotest_dirname, os.path.basename(dest_dir)))

    def get_last_guest_results_index():
        res_index = 0
        for subpath in os.listdir(outputdir):
            if re.search("guest_autotest_results\d+", subpath):
                res_index = max(
                    res_index, int(re.search("guest_autotest_results(\d+)", subpath).group(1)))
        return res_index

    def get_results(base_results_dir):
        """
        Copy autotest results present on the guest back to the host.
        """
        logging.debug("Trying to copy autotest results from guest")
        res_index = get_last_guest_results_index()
        guest_results_dir = os.path.join(
            outputdir, "guest_autotest_results%s" % (res_index + 1))
        os.mkdir(guest_results_dir)
        # result info tarball to host result dir
        session = vm.wait_for_login(timeout=360)
        results_dir = "%s/results/default" % base_results_dir
        results_tarball = os.path.join(data_dir.get_tmp_dir(), "results.tgz")
        compress_cmd = "cd %s && " % results_dir
        compress_cmd += "tar cjvf %s ./*" % results_tarball
        compress_cmd += " --exclude=*core*"
        compress_cmd += " --exclude=*crash*"
        session.cmd(compress_cmd, timeout=600)
        vm.copy_files_from(results_tarball, guest_results_dir)
        # cleanup autotest subprocess which not terminated, change PWD to
        # avoid current connection kill by fuser command;
        clean_cmd = "cd /tmp && fuser -k %s" % results_dir
        session.sendline(clean_cmd)
        session.cmd("rm -f %s" % results_tarball, timeout=240)
        results_tarball = os.path.basename(results_tarball)
        results_tarball = os.path.join(guest_results_dir, results_tarball)
        uncompress_cmd = "tar xjvf %s -C %s" % (results_tarball,
                                                guest_results_dir)
        process.run(uncompress_cmd)
        process.run("rm -f %s" % results_tarball)

    def get_results_summary():
        """
        Get the status of the tests that were executed on the guest.
        NOTE: This function depends on the results copied to host by
              get_results() function, so call get_results() first.
        """
        res_index = get_last_guest_results_index()
        base_dir = os.path.join(
            outputdir, "guest_autotest_results%s" % res_index)
        status_paths = glob.glob(os.path.join(base_dir, "*/status"))
        # for control files that do not use job.run_test()
        status_no_job = os.path.join(base_dir, "status")
        if os.path.exists(status_no_job):
            status_paths.append(status_no_job)
        status_path = " ".join(status_paths)

        try:
            output = process.system_output("cat %s" % status_path)
        except process.CmdError, e:
            logging.error("Error getting guest autotest status file: %s", e)
            return None

        try:
            results = scan_autotest_results.parse_results(output)
            # Report test results
            logging.info("Results (test, status, duration, info):")
            for result in results:
                logging.info("\t %s", str(result))
            return results
        except Exception, e:
            logging.error("Error processing guest autotest results: %s", e)
            return None

    def config_control(control_path, job_args=None):
        """
        Edit the control file to adapt the current environment.

        Replace CLIENTIP with guestip, and replace SERVERIP with hostip.
        Support to pass arguments for client jobs.
        For example:
            stress args: job.run_test('stress', args="...")
            so job_args can be {'args': "..."}, they should be arguments
            of this job.

        :return: Path of a temp file which contains the result of replacing.
        """
        pattern2repl_dict = {r'CLIENTIP': vm.get_address(),
                             r'SERVERIP': utils_net.get_host_ip_address(params)}
        control_file = open(control_path)
        lines = control_file.readlines()
        control_file.close()

        for pattern, repl in pattern2repl_dict.items():
            for index in range(len(lines)):
                line = lines[index]
                lines[index] = re.sub(pattern, repl, line)

        # Provided arguments need to be added
        if job_args is not None and isinstance(job_args, dict):
            newlines = []
            for index in range(len(lines)):
                line = lines[index]
                # Only job lines need to be configured now
                if re.search("job.run_test", line):
                    # Get job type
                    allargs = line.split('(')[1].split(',')
                    if len(allargs) > 1:
                        job_type = allargs[0]
                    elif len(allargs) == 1:
                        job_type = allargs[0].split(')')[0]
                    else:
                        job_type = ""
                    # Assemble job function
                    jobline = "job.run_test(%s" % job_type
                    for key, value in job_args.items():
                        jobline += ", %s='%s'" % (key, value)
                    jobline += ")\n"
                    newlines.append(jobline)
                    break   # No need following lines
                else:
                    # None of these lines' business
                    newlines.append(line)
            lines = newlines

        fd, temp_control_path = tempfile.mkstemp(prefix="control",
                                                 dir=data_dir.get_tmp_dir())
        os.close(fd)

        temp_control = open(temp_control_path, "w")
        temp_control.writelines(lines)
        temp_control.close()
        return temp_control_path

    migrate_background = params.get("migrate_background") == "yes"
    if migrate_background:
        mig_timeout = float(params.get("mig_timeout", "3600"))
        mig_protocol = params.get("migration_protocol", "tcp")

    compressed_autotest_path = os.path.join(data_dir.get_tmp_dir(),
                                            "autotest.tar.bz2")
    destination_autotest_path = "/usr/local/autotest"

    # To avoid problems, let's make the test use the current AUTODIR
    # (autotest client path) location
    from autotest.client import common
    from autotest.client.shared import base_packages
    autotest_path = os.path.dirname(common.__file__)
    autotest_local_path = os.path.join(autotest_path, 'autotest-local')
    single_dir_install = os.path.isfile(autotest_local_path)
    if not single_dir_install:
        autotest_local_path = path.find_command('autotest-local')
    kernel_install_path = os.path.join(autotest_path, 'tests',
                                       'kernelinstall')
    kernel_install_present = os.path.isdir(kernel_install_path)
    autotest_basename = os.path.basename(autotest_path)
    autotest_parentdir = os.path.dirname(autotest_path)

    # tar the contents of bindir/autotest
    if base_packages.has_pbzip2():
        tar_cmds = "--use-compress-program=pbzip2 -cvf"
    else:
        tar_cmds = "cvjf"
    cmd = ("cd %s; tar %s %s %s/*" %
           (autotest_parentdir, tar_cmds,
            compressed_autotest_path, autotest_basename))
    cmd += " --exclude=%s/results*" % autotest_basename
    cmd += " --exclude=%s/tmp" % autotest_basename
    cmd += " --exclude=%s/control*" % autotest_basename
    cmd += " --exclude=*.pyc"
    cmd += " --exclude=*.svn"
    cmd += " --exclude=*.git"
    virt_dir = os.path.join(autotest_basename, 'tests', 'virt')
    if os.path.isdir(virt_dir):
        cmd += " --exclude=%s" % virt_dir
    process.run(cmd, shell=True)

    # Install autotest and autotest client tests to guest
    autotest_tarball = copy_if_hash_differs(vm, compressed_autotest_path,
                                            compressed_autotest_path)
    if autotest_tarball or not directory_exists(destination_autotest_path):
        extract(vm, autotest_tarball, destination_autotest_path)
        tests_dir = "%s/tests" % destination_autotest_path
        if not directory_exists(tests_dir):
            tarball_url = ("https://codeload.github.com/autotest/"
                           "autotest-client-tests/tar.gz/master")
            tarball_url = params.get("client_test_url", tarball_url)
            tests_timeout = int(params.get("download_tests_timeout", "600"))
            tests_tarball = os.path.join(data_dir.get_tmp_dir(), "tests.tgz")
            download.url_download(
                tarball_url,
                tests_tarball,
                timeout=tests_timeout)
            copy_if_hash_differs(vm, tests_tarball, tests_tarball)
            extract(vm, tests_tarball, tests_dir)
            os.remove(tests_tarball)

    if os.path.exists(compressed_autotest_path):
        os.remove(compressed_autotest_path)

    g_fd, g_path = tempfile.mkstemp(dir=data_dir.get_tmp_dir())
    aux_file = os.fdopen(g_fd, 'w')
    try:
        config = section_values(('CLIENT', 'COMMON'))
    except Exception:
        # Leak global_config.ini, generate a mini configuration
        # to ensure client tests can work.
        import ConfigParser
        config = ConfigParser.ConfigParser()
        map(config.add_section, ['CLIENT', 'COMMON'])
        config.set('COMMON', 'crash_handling_enabled', 'True')
    config.set('CLIENT', 'output_dir', destination_autotest_path)
    config.set('COMMON', 'autotest_top_path', destination_autotest_path)
    destination_test_dir = os.path.join(destination_autotest_path, 'tests')
    config.set('COMMON', 'test_dir', destination_test_dir)
    destination_test_output_dir = os.path.join(destination_autotest_path,
                                               'results')
    config.set('COMMON', 'test_output_dir', destination_test_output_dir)
    config.write(aux_file)
    aux_file.close()
    global_config_guest = os.path.join(destination_autotest_path,
                                       'global_config.ini')
    vm.copy_files_to(g_path, global_config_guest)
    os.unlink(g_path)

    if not single_dir_install:
        vm.copy_files_to(autotest_local_path,
                         os.path.join(destination_autotest_path,
                                      'autotest-local'))

    # Support autotests that are in client-server model.
    server_control_path = None
    if os.path.isdir(control_path):
        server_control_path = os.path.join(control_path, "control.server")
        server_control_path = config_control(server_control_path)
        control_path = os.path.join(control_path, "control.client")
    # Edit control file and copy it to vm.
    if control_args is not None:
        job_args = {'args': control_args}
    else:
        job_args = None
    temp_control_path = config_control(control_path, job_args=job_args)
    vm.copy_files_to(temp_control_path,
                     os.path.join(destination_autotest_path, 'control'))

    # remove the temp control file.
    if os.path.exists(temp_control_path):
        os.remove(temp_control_path)

    if not kernel_install_present:
        kernel_install_dir = os.path.join(data_dir.get_root_dir(),
                                          "shared", "deps", "run_autotest",
                                          "kernel_install")
        kernel_install_dest = os.path.join(destination_autotest_path, 'tests',
                                           'kernelinstall')
        vm.copy_files_to(kernel_install_dir, kernel_install_dest)
        import virttest
        module_dir = os.path.dirname(virttest.__file__)
        utils_koji_file = os.path.join(module_dir, 'staging', 'utils_koji.py')
        vm.copy_files_to(utils_koji_file, kernel_install_dest)

    # Copy a non crippled boottool and make it executable
    boottool_path = os.path.join(data_dir.get_root_dir(),
                                 "shared", "deps", "run_autotest",
                                 "boottool.py")
    boottool_dest = '/usr/local/autotest/tools/boottool.py'
    vm.copy_files_to(boottool_path, boottool_dest)
    session.cmd("chmod +x %s" % boottool_dest)

    # Clean the environment.
    session.cmd("cd %s" % destination_autotest_path)
    try:
        session.cmd("rm -f control.state")
        session.cmd("rm -rf results/*")
        session.cmd("rm -rf tmp/*")
    except aexpect.ShellError:
        pass

    # Check copy_only.
    if copy_only:
        return ("python -x %s/autotest-local --verbose %s/control" %
                (destination_autotest_path, destination_autotest_path))

    # Run the test
    logging.info("Running autotest control file %s on guest, timeout %ss",
                 os.path.basename(control_path), timeout)

    # Start a background job to run server process if needed.
    server_process = None
    if server_control_path:
        job_tag = os.path.basename(server_control_path)
        command = ("python -x %s %s --verbose -t %s" % (autotest_local_path,
                                                        server_control_path,
                                                        job_tag))
        server_process = aexpect.run_bg(command)

    try:
        bg = None
        try:
            start_time = time.time()
            logging.info("---------------- Test output ----------------")
            if migrate_background:
                mig_timeout = float(params.get("mig_timeout", "3600"))
                mig_protocol = params.get("migration_protocol", "tcp")
                cmd = "python -x ./autotest-local control"
                kwargs = {'cmd': cmd,
                          'timeout': timeout,
                          'print_func': logging.info}
                bg = utils_misc.InterruptedThread(session.cmd_output,
                                                  kwargs=kwargs)
                bg.start()

                while bg.isAlive():
                    logging.info("Autotest job did not end, start a round of "
                                 "migration")
                    vm.migrate(timeout=mig_timeout, protocol=mig_protocol)
            else:
                if params.get("guest_autotest_verbosity", "yes") == "yes":
                    verbose = " --verbose"
                else:
                    verbose = ""
                session.cmd_output(
                    "python -x ./autotest-local %s control & wait ${!}" %
                    verbose,
                    timeout=timeout,
                    print_func=logging.info)
        finally:
            logging.info("------------- End of test output ------------")
            if migrate_background and bg:
                bg.join()
            # Do some cleanup work on host if test need a server.
            if server_process:
                if server_process.is_alive():
                    utils_misc.kill_process_tree(server_process.get_pid(),
                                                 signal.SIGINT)
                server_process.close()

                # Remove the result dir produced by server_process.
                job_tag = os.path.basename(server_control_path)
                server_result = os.path.join(autotest_path,
                                             "results", job_tag)
                if os.path.isdir(server_result):
                    utils_misc.safe_rmdir(server_result)
                # Remove the control file for server.
                if os.path.exists(server_control_path):
                    os.remove(server_control_path)

    except aexpect.ShellTimeoutError:
        if vm.is_alive():
            get_results(destination_autotest_path)
            get_results_summary()
            raise exceptions.TestError("Timeout elapsed while waiting "
                                       "for job to complete")
        else:
            raise exceptions.TestError("Autotest job on guest failed "
                                       "(VM terminated during job)")
    except aexpect.ShellProcessTerminatedError:
        if ignore_session_terminated:
            try:
                vm.verify_alive()
            except Exception:
                get_results(destination_autotest_path)
                raise exceptions.TestError("Autotest job on guest failed "
                                           "(VM terminated during job)")
            logging.debug("Wait for autotest job finished on guest.")
            session.close()
            session = vm.wait_for_login()
            while time.time() < start_time + timeout:
                ps_cmd = "ps ax"
                _, processes = session.cmd_status_output(ps_cmd)
                if "autotest-local" not in processes:
                    logging.debug("Autotest job finished on guest")
                    break
                time.sleep(1)
            else:
                get_results(destination_autotest_path)
                get_results_summary()
                raise exceptions.TestError("Timeout elapsed while waiting "
                                           "for job to complete")
        else:
            get_results(destination_autotest_path)
            raise exceptions.TestError("Autotest job on guest failed "
                                       "(Remote session terminated during job)")

    get_results(destination_autotest_path)
    results = get_results_summary()

    if results is not None:
        # Make a list of FAIL/ERROR/ABORT results (make sure FAIL results appear
        # before ERROR results, and ERROR results appear before ABORT results)
        bad_results = [r[0] for r in results if r[1] == "FAIL"]
        bad_results += [r[0] for r in results if r[1] == "ERROR"]
        bad_results += [r[0] for r in results if r[1] == "ABORT"]

    # Fail the test if necessary
    if not results:
        raise exceptions.TestFail("Autotest control file run did not "
                                  "produce any recognizable results")
    if bad_results:
        if len(bad_results) == 1:
            e_msg = ("Test %s failed during control file execution" %
                     bad_results[0])
        else:
            e_msg = ("Tests %s failed during control file execution" %
                     " ".join(bad_results))
        raise exceptions.TestFail(e_msg)


def get_loss_ratio(output):
    """
    Get the packet loss ratio from the output of ping.

    :param output: Ping output.
    """
    try:
        return int(re.findall('(\d+)%.*loss', output)[0])
    except IndexError:
        logging.warn("Invaild output of ping command: %s" % output)
    return -1


def run_virt_sub_test(test, params, env, sub_type=None, tag=None):
    """
    Call another test script in one test script.
    :param test:   Virt Test object.
    :param params: Dictionary with the test parameters.
    :param env:    Dictionary with test environment.
    :param sub_type: Type of called test script.
    :param tag:    Tag for get the sub_test params
    """
    if sub_type is None:
        raise exceptions.TestError("Unspecified sub test type. Please specify a"
                                   "sub test type")

    provider = params.get("provider", None)
    subtest_dirs = []
    subtest_dir = None

    if provider is None:
        # Verify if we have the correspondent source file for it
        for generic_subdir in asset.get_test_provider_subdirs('generic'):
            subtest_dirs += data_dir.SubdirList(generic_subdir,
                                                bootstrap.test_filter)
        for multi_host_migration_subdir in asset.get_test_provider_subdirs(
                'multi_host_migration'):
            subtest_dirs += data_dir.SubdirList(multi_host_migration_subdir,
                                                bootstrap.test_filter)

        for specific_subdir in asset.get_test_provider_subdirs(
                params.get("vm_type")):
            subtest_dirs += data_dir.SubdirList(specific_subdir,
                                                bootstrap.test_filter)
    else:
        provider_info = asset.get_test_provider_info(provider)
        for key in provider_info['backends']:
            subtest_dirs += data_dir.SubdirList(
                provider_info['backends'][key]['path'],
                bootstrap.test_filter)

    for d in subtest_dirs:
        module_path = os.path.join(d, "%s.py" % sub_type)
        if os.path.isfile(module_path):
            subtest_dir = d
            break

    if subtest_dir is None:
        raise exceptions.TestError("Could not find test file %s.py "
                                   "on directories %s" % (sub_type, subtest_dirs))

    f, p, d = imp.find_module(sub_type, [subtest_dir])
    test_module = imp.load_module(sub_type, f, p, d)
    f.close()
    # Run the test function
    run_func = utils_misc.get_test_entrypoint_func(sub_type, test_module)
    if tag is not None:
        params = params.object_params(tag)
    run_func(test, params, env)


def get_readable_cdroms(params, session):
    """
    Get the cdrom list which contain media in guest.

    :param params: Dictionary with the test parameters.
    :param session: A shell session on the VM provided.
    """
    get_cdrom_cmd = params.get("cdrom_get_cdrom_cmd")
    check_cdrom_patttern = params.get("cdrom_check_cdrom_pattern")
    o = session.get_command_output(get_cdrom_cmd)
    cdrom_list = re.findall(check_cdrom_patttern, o)
    logging.debug("Found cdroms on guest: %s" % cdrom_list)

    readable_cdroms = []
    test_cmd = params.get("cdrom_test_cmd")
    for d in cdrom_list:
        s, o = session.cmd_status_output(test_cmd % d)
        if s == 0:
            readable_cdroms.append(d)
            break
    if not readable_cdroms:
        info_cmd = params.get("cdrom_info_cmd")
        output = session.cmd_output(info_cmd)
        logging.debug("Guest cdroms info: %s" % output)
    return readable_cdroms


def service_setup(vm, session, directory):

    params = vm.get_params()
    rh_perf_envsetup_script = params.get("rh_perf_envsetup_script")
    rebooted = params.get("rebooted", "rebooted")

    if rh_perf_envsetup_script:
        src = os.path.join(directory, rh_perf_envsetup_script)
        vm.copy_files_to(src, "/tmp/rh_perf_envsetup.sh")
        logging.info("setup perf environment for host")
        commands.getoutput("bash %s host %s" % (src, rebooted))
        logging.info("setup perf environment for guest")
        session.cmd("bash /tmp/rh_perf_envsetup.sh guest %s" % rebooted)


def summary_up_result(result_file, ignore, row_head, column_mark):
    """
    Use to summary the monitor or other kinds of results. Now it calculates
    the average value for each item in the results. It fits to the records
    that are in matrix form.

    @result_file: files which need to calculate
    @ignore: pattern for the comment in results which need to through away
    @row_head: pattern for the items in row
    @column_mark: pattern for the first line in matrix which used to generate
    the items in column
    :return: A dictionary with the average value of results
    """
    head_flag = False
    result_dict = {}
    column_list = {}
    row_list = []
    fd = open(result_file, "r")
    for eachLine in fd:
        if len(re.findall(ignore, eachLine)) == 0:
            if len(re.findall(column_mark, eachLine)) != 0 and not head_flag:
                column = 0
                _, row, eachLine = re.split(row_head, eachLine)
                for i in re.split("\s+", eachLine):
                    if i:
                        result_dict[i] = {}
                        column_list[column] = i
                        column += 1
                head_flag = True
            elif len(re.findall(column_mark, eachLine)) == 0:
                column = 0
                _, row, eachLine = re.split(row_head, eachLine)
                row_flag = False
                for i in row_list:
                    if row == i:
                        row_flag = True
                if row_flag is False:
                    row_list.append(row)
                    for i in result_dict:
                        result_dict[i][row] = []
                for i in re.split("\s+", eachLine):
                    if i:
                        result_dict[column_list[column]][row].append(i)
                        column += 1
    fd.close()
    # Calculate the average value
    average_list = {}
    for i in column_list:
        average_list[column_list[i]] = {}
        for j in row_list:
            average_list[column_list[i]][j] = {}
            check = result_dict[column_list[i]][j][0]
            if utils_misc.aton(check) or utils_misc.aton(check) == 0.0:
                count = 0
                for k in result_dict[column_list[i]][j]:
                    count += utils_misc.aton(k)
                average_list[column_list[i]][j] = "%.2f" % (count /
                                                            len(result_dict[column_list[i]][j]))

    return average_list


def get_driver_hardware_id(driver_path,
                           mount_point=os.path.join(data_dir.get_tmp_dir(),
                                                    "mnt-virtio"),
                           storage_path=os.path.join(data_dir.get_tmp_dir(),
                                                     "prewhql.iso"),
                           re_hw_id="(PCI.{14,50})", run_cmd=True):
    """
    Get windows driver's hardware id from inf files.

    :param dirver: Configurable driver name.
    :param mount_point: Mount point for the driver storage
    :param storage_path: The path of the virtio driver storage
    :param re_hw_id: the pattern for getting hardware id from inf files
    :param run_cmd:  Use hardware id in windows cmd command or not

    :return: Windows driver's hardware id
    """
    if not os.path.exists(mount_point):
        os.mkdir(mount_point)

    if not os.path.ismount(mount_point):
        process.system("mount %s %s -o loop" % (storage_path, mount_point),
                       timeout=60)
    driver_link = os.path.join(mount_point, driver_path)
    txt_file = ""
    try:
        txt_file = open(driver_link, "r")
        txt = txt_file.read()
        hwid = re.findall(re_hw_id, txt)[-1].rstrip()
        if run_cmd:
            hwid = '^&'.join(hwid.split('&'))
        txt_file.close()
        process.system("umount %s" % mount_point)
        return hwid
    except Exception, e:
        logging.error("Fail to get hardware id with exception: %s" % e)
        if txt_file:
            txt_file.close()
        process.system("umount %s" % mount_point, ignore_status=True)
        return ""


class BackgroundTest(object):

    """
    This class would run a test in background through a dedicated thread.
    """

    def __init__(self, func, params, kwargs={}):
        """
        Initialize the object and set a few attributes.
        """
        self.thread = threading.Thread(target=self.launch,
                                       args=(func, params, kwargs))
        self.exception = None

    def launch(self, func, params, kwargs):
        """
        Catch and record the exception.
        """
        try:
            func(*params, **kwargs)
        except Exception, e:
            self.exception = e

    def start(self):
        """
        Run func(params) in a dedicated thread
        """
        self.thread.start()

    def join(self, timeout=600, ignore_status=False):
        """
        Wait for the join of thread and raise its exception if any.
        """
        self.thread.join(timeout)
        # pylint: disable=E0702
        if self.exception and (not ignore_status):
            raise self.exception

    def is_alive(self):
        """
        Check whether the test is still alive.
        """
        return self.thread.isAlive()


def get_image_info(image_file):
    return utils_misc.get_image_info(image_file)


def ntpdate(service_ip, session=None):
    """
    set the date and time via NTP
    """
    try:
        ntpdate_cmd = "ntpdate %s" % service_ip
        if session:
            session.cmd(ntpdate_cmd)
        else:
            process.run(ntpdate_cmd)
    except (process.CmdError, aexpect.ShellError), detail:
        raise exceptions.TestFail(
            "Failed to set the date and time. %s" % detail)


def get_date(session=None):
    """
    Get the date time
    """
    try:
        date_cmd = "date +%s"
        if session:
            date_info = session.cmd_output(date_cmd).strip()
        else:
            date_info = process.run(date_cmd).stdout.strip()
        return date_info
    except (process.CmdError, aexpect.ShellError), detail:
        raise exceptions.TestFail("Get date failed. %s " % detail)


def run_avocado_bg(vm, params, test):
    """
    Function to run avocado tests inside guest in background

    :param vm: VM object
    :param params: VM param
    :param test: test object
    :return: background test thread
    """
    testlist = []
    avocado_test = params.get("avocado_test", "")
    avocado_mux = params.get("avocado_mux", "")
    avocado_testargs = params.get("avocado_testargs", "")
    avocado_timeout = int(params.get("avocado_timeout", 3600))
    avocado_testrepo = params.get("avocado_testrepo",
                                  "https://github.com/avocado-framework-tests/avocado-misc-tests.git")
    for index, item in enumerate(avocado_test.split(',')):
        try:
            mux = ''
            mux = avocado_mux.split(',')[index]
        except IndexError:
            pass
        testlist.append((item, mux))
    if testlist:
        bt = BackgroundTest(run_avocado,
                            [vm, params, test, testlist,
                             avocado_timeout, avocado_testrepo, "pip",
                             True, avocado_testargs, True])
        bt.start()
        return bt
    else:
        logging.warning("Background guest tests not run")
        return None


# Stress functions################
class StressError(Exception):

    """
    Stress test exception.
    """

    def __init__(self, msg):
        Exception.__init__(self, msg)
        self.msg = msg

    def __str__(self):
        return self.msg


class VMStress(object):

    """
    Run Stress tool in vms, such as stress, unixbench, iozone and etc.
    """

    def __init__(self, vm, stress_type):
        """
        Set parameters for stress type
        """

        def _parameters_filter(stress_type):
            """Set parameters according stress_type"""
            _control_files = {'unixbench': "unixbench5.control",
                              'stress': "stress.control",
                              'iozone': "iozone.control"}
            _check_cmds = {'unixbench': "pidof -s ./Run",
                           'stress': "pidof -s stress",
                           'iozone': "pidof -s iozone"}
            _stop_cmds = {'unixbench': "killall ./Run",
                          'stress': "killall stress",
                          'iozone': "killall iozone"}
            try:
                control_file = _control_files[stress_type]
                self.control_path = os.path.join(data_dir.get_root_dir(),
                                                 "shared/control",
                                                 control_file)
                self.check_cmd = _check_cmds[stress_type]
                self.stop_cmd = _stop_cmds[stress_type]
            except KeyError:
                self.control_path = ""
                self.check_cmd = ""
                self.stop_cmd = ""

        self.vm = vm
        self.params = vm.params
        self.timeout = 60
        self.stress_type = stress_type
        if stress_type not in ["stress", "unixbench", "iozone"]:
            raise StressError("Stress %s is not supported now." % stress_type)

        _parameters_filter(stress_type)
        self.stress_args = self.params.get("stress_args", "")

    def get_session(self):
        try:
            session = self.vm.wait_for_login()
            return session
        except aexpect.ShellError, detail:
            raise StressError("Login %s failed:\n%s" % (self.vm.name, detail))

    @error_context.context_aware
    def load_stress_tool(self):
        """
        load stress tool in guest
        """
        session = self.get_session()
        command = run_autotest(self.vm, session, self.control_path,
                               None, None, self.params, copy_only=True,
                               control_args=self.stress_args)
        session.cmd("%s &" % command)
        logging.info("Command: %s", command)
        running = utils_misc.wait_for(self.app_running, first=0.5, timeout=60)
        if not running:
            raise StressError("Stress tool %s isn't running"
                              % self.stress_type)

    @error_context.context_aware
    def unload_stress(self):
        """
        stop stress tool manually
        """
        def _unload_stress():
            session = self.get_session()
            session.sendline(self.stop_cmd)
            if not self.app_running():
                return True
            return False

        error_context.context("stop stress app in guest", logging.info)
        utils_misc.wait_for(_unload_stress, first=2.0,
                            text="wait stress app quit", step=1.0, timeout=60)

    def app_running(self):
        """
        check whether app really run in background
        """
        session = self.get_session()
        status = session.cmd_status(self.check_cmd, timeout=60)
        return status == 0


class HostStress(object):

    """
    Run Stress tool on host, such as stress, unixbench, iozone and etc.
    """

    def __init__(self, params, stress_type):
        """
        Set parameters for stress type
        """

        def _parameters_filter(stress_type):
            """Set parameters according stress_type"""
            _control_files = {'unixbench': "unixbench5.control",
                              'stress': "stress.control"}
            _check_cmds = {'unixbench': "pidof -s ./Run",
                           'stress': "pidof -s stress"}
            _stop_cmds = {'unixbench': "killall ./Run",
                          'stress': "killall stress"}
            try:
                control_file = _control_files[stress_type]
                self.control_path = os.path.join(data_dir.get_root_dir(),
                                                 "shared/control",
                                                 control_file)
                self.check_cmd = _check_cmds[stress_type]
                self.stop_cmd = _stop_cmds[stress_type]
            except KeyError:
                self.control_path = ""
                self.check_cmd = ""
                self.stop_cmd = ""

        self.params = {}
        if params:
            self.params = params
        self.timeout = 60
        self.stress_type = stress_type
        self.host_stress_process = None
        if stress_type not in ["stress", "unixbench"]:
            raise StressError("Stress %s is not supported now." % stress_type)

        _parameters_filter(stress_type)
        self.stress_args = self.params.get("stress_args", "")

    @error_context.context_aware
    def load_stress_tool(self):
        """
        load stress tool on host.
        """
        # Run stress tool on host.
        try:
            path.find_command(self.stress_type)
        except path.CmdNotFoundError, detail:
            raise exceptions.TestSkipError("Stress tool %s is missing: %s"
                                           % (self.stress_type, str(detail)))

        args = [self.stress_type, '--args=%s' % self.stress_args,
                '--verbose']
        logging.info("Start sub-process by args: %s", args)
        self.host_stress_process = subprocess.Popen(args,
                                                    stdout=subprocess.PIPE,
                                                    stderr=subprocess.PIPE)
        running = utils_misc.wait_for(self.app_running, first=0.5, timeout=60)
        if not running:
            raise StressError("Stress tool %s isn't running"
                              % self.stress_type)

    @error_context.context_aware
    def unload_stress(self):
        """
        stop stress tool manually
        """
        def _unload_stress():
            if self.host_stress_process is not None:
                utils_misc.kill_process_tree(self.host_stress_process.pid)
            if not self.app_running():
                return True
            return False

        error_context.context("stop stress app on host", logging.info)
        utils_misc.wait_for(_unload_stress, first=2.0,
                            text="wait stress app quit", step=1.0, timeout=60)

    def app_running(self):
        """
        check whether app really run in background
        """
        result = process.run(self.check_cmd, timeout=60, ignore_status=True)
        return result.exit_status == 0


def load_stress(stress_type, vms, params):
    """
    Load stress for tests.

    :param stress_type: The stress type you need
    :param params: Useful parameters for stress
    :param vms: Used when it's stress in vms
    """
    fail_info = []
    # Add stress/iozone tool in vms
    if stress_type in ['stress_in_vms', 'iozone_in_vms']:
        for vm in vms:
            try:
                vstress = VMStress(vm, stress_type.split('_')[0])
                vstress.load_stress_tool()
            except StressError, detail:
                fail_info.append("Launch stress in %s failed: %s"
                                 % (vm.name, detail))
    # Add stress for host
    elif stress_type == "stress_on_host":
        try:
            hstress = HostStress(params, "stress")
            hstress.load_stress_tool()
        except StressError, detail:
            fail_info.append("Launch stress on host failed: %s" % str(detail))
    # Booting vm for following test
    elif stress_type == "load_vm_booting":
        load_vms = params.get("load_vms", [])
        if len(load_vms):
            load_vm = load_vms[0]
            try:
                if load_vm.is_alive():
                    load_vm.destroy()
                load_vm.start()
            except virt_vm.VMStartError:
                fail_info.append("Start load vm %s failed." % load_vm.name)
        else:
            fail_info.append("No load vm provided.")
    # Booting vms for following test
    elif stress_type == "load_vms_booting":
        load_vms = params.get("load_vms", [])
        for load_vm in load_vms:
            if load_vm.is_alive():
                load_vm.destroy()
        # Booting load_vms at same time
        for load_vm in load_vms:
            try:
                load_vm.start()
            except virt_vm.VMStartError:
                fail_info.append("Start load vm %s failed." % load_vm.name)
                break
    # Booting test vms for following test
    elif stress_type == "vms_booting":
        for vm in vms:
            if vm.is_alive():
                vm.destroy()
        try:
            for vm in vms:
                vm.start()
        except virt_vm.VMStartError:
            fail_info.append("Start vms failed.")
    return fail_info


def unload_stress(stress_type, vms):
    """
    Unload stress loaded by load_stress(...).
    """
    if stress_type == "stress_in_vms":
        for vm in vms:
            VMStress(vm, "stress").unload_stress()
    elif stress_type == "stress_on_host":
        HostStress(None, "stress").unload_stress()


class RemoteDiskManager(object):

    """Control images on remote host"""

    def __init__(self, params):
        remote_host = params.get("remote_ip")
        remote_user = params.get("remote_user")
        remote_pwd = params.get("remote_pwd")
        self.runner = remote.RemoteRunner(host=remote_host,
                                          username=remote_user,
                                          password=remote_pwd)

    def get_free_space(self, disk_type, path='/', vgname=None):
        """
        Get free space of remote host for path.

        :return : the unit is 'G'.
        """
        if disk_type == "file":
            cmd = "df -BG %s" % os.path.dirname(path)
        elif disk_type == "lvm":
            cmd = "vgs --units=g | grep %s" % vgname
        else:
            raise exceptions.TestError("Unsupported Disk Type %s" % disk_type)

        try:
            output = self.runner.run(cmd).stdout
        except exceptions.CmdError, detail:
            logging.debug(output)
            raise exceptions.TestError("Get space failed: %s." % str(detail))

        if disk_type == "file":
            try:
                return int(output.splitlines()[1].split()[3].split('G')[0])
            except IndexError, detail:
                raise exceptions.TestError("Get %s space failed: %s." %
                                           (os.path.dirname(path), str(detail)))
        elif disk_type == "lvm":
            if re.search(vgname, output):
                try:
                    # "int('50.00')" will ValueError, so needs float()
                    return int(float(output.split()[6].split('g')[0]))
                except (IndexError, ValueError), detail:
                    raise exceptions.TestError("Get %s space failed: %s." %
                                               (vgname, str(detail)))
            else:
                raise exceptions.TestError("Get %s space failed: %s." %
                                           (vgname, output))

    def occupy_space(self, disk_type, need_size, path=None, vgname=None,
                     timeout=60):
        """
        Create an image or volume to occupy the space of destination path
        """
        free = self.get_free_space(disk_type, path, vgname)
        logging.debug("Allowed space on remote path:%sGB", free)
        occupied_size = free - need_size / 2
        occupied_path = os.path.join(os.path.dirname(path), "occupied")
        return self.create_image(disk_type, occupied_path, occupied_size,
                                 vgname, "occupied", False, timeout)

    def iscsi_login_setup(self, host, target_name, is_login=True):
        """
        Login or logout to a target on remote host.
        """
        if is_login:
            discovery_cmd = "iscsiadm -m discovery -t sendtargets -p %s" % host
            output = self.runner.run(discovery_cmd, ignore_status=True).stdout
            if target_name not in output:
                raise exceptions.TestError("Discovery %s on %s failed."
                                           % (target_name, host))
            cmd = "iscsiadm --mode node --login --targetname %s" % target_name
            output = self.runner.run(cmd).stdout
            if "successful" not in output:
                raise exceptions.TestError("Login to %s failed." % target_name)
            else:
                cmd = "iscsiadm -m session -P 3"
                output = self.runner.run(cmd).stdout
                pattern = r"Target:\s+%s.*?disk\s(\w+)\s+\S+\srunning" % target_name
                device_name = re.findall(pattern, output, re.S)
                try:
                    return "/dev/%s" % device_name[0]
                except IndexError:
                    raise exceptions.TestError("Can not find target '%s' after login."
                                               % self.target)
        else:
            if target_name:
                cmd = "iscsiadm --mode node --logout -T %s" % target_name
            else:
                cmd = "iscsiadm --mode node --logout all"
            output = self.runner.run(cmd, ignore_status=True).stdout
            if "successful" not in output:
                logging.error("Logout to %s failed.", target_name)

    def create_vg(self, vgname, device):
        """
        Create volume group with provided device.
        """
        try:
            self.runner.run("vgs | grep %s" % vgname)
            logging.debug("Volume group %s does already exist.", vgname)
            return True
        except process.CmdError:
            pass    # Not found
        try:
            self.runner.run("vgcreate %s %s" % (vgname, device))
            return True
        except process.CmdError, detail:
            logging.error("Create vgroup '%s' on remote host failed:%s",
                          vgname, detail)
            return False

    def remove_vg(self, vgname):
        """
        Remove volume group on remote host.
        """
        try:
            self.runner.run("vgremove -f %s" % vgname)
        except process.CmdError:
            return False
        return True

    def create_image(self, disk_type, path=None, size=10, vgname=None,
                     lvname=None, sparse=True, timeout=60, img_frmt=None):
        """
        Create an image for target path.
        """
        if disk_type == "file":
            self.runner.run("mkdir -p %s" % os.path.dirname(path))
            if not os.path.basename(path):
                path = os.path.join(path, "temp.img")
            cmd = "qemu-img create"
            if img_frmt is not None:
                cmd += " -f %s" % img_frmt
            if sparse:
                cmd += " %s %sG" % (path, size)
            else:
                cmd = "dd if=/dev/zero of=%s bs=1G count=%s" % (path, size)
        elif disk_type == "lvm":
            if sparse:
                cmd = "lvcreate -V %sG %s --name %s --size 1M" % (size, vgname,
                                                                  lvname)
            else:
                cmd = "lvcreate -L %sG %s --name %s" % (size, vgname, lvname)
            path = "/dev/%s/%s" % (vgname, lvname)

        result = self.runner.run(cmd, ignore_status=True, timeout=timeout)
        logging.debug(result)
        if result.exit_status:
            raise exceptions.TestFail("Create image '%s' on remote host failed."
                                      % path)
        else:
            return path

    def remove_path(self, disk_type, path):
        """
        Only allowed to remove path to file or volume.
        """
        if disk_type == "file":
            if os.path.isdir(path):
                return
            self.runner.run("rm -f %s" % path, ignore_status=True)
        elif disk_type == "lvm":
            self.runner.run("lvremove -f %s" % path, ignore_status=True)


def check_dest_vm_network(vm, vm_ip, remote_host, username, password,
                          shell_prompt=r"[\#\$]\s*$", timeout=60):
    """
    Ping migrated vms on remote host.
    """
    runner = remote.RemoteRunner(host=remote_host,
                                 username=username,
                                 password=password,
                                 prompt=shell_prompt)

    logging.debug("Check VM network connectivity...")
    ping_failed = True
    ping_cmd = "ping -c 5 %s" % vm_ip
    while timeout > 0:
        result = runner.run(ping_cmd, ignore_status=True)
        if result.exit_status:
            time.sleep(5)
            timeout -= 5
            continue
        ping_failed = False
        break
    if ping_failed:
        raise exceptions.TestFail("Failed to ping %s: %s" % (vm.name,
                                                             result.stdout))


class RemoteVMManager(object):

    """Manage VM on remote host"""

    def __init__(self, params):
        self.remote_host = params.get("server_ip")
        self.remote_user = params.get("server_user")
        self.remote_pwd = params.get("server_pwd")
        self.runner = remote.RemoteRunner(host=self.remote_host,
                                          username=self.remote_user,
                                          password=self.remote_pwd)

    def setup_ssh_auth(self, vm_ip, vm_pwd, vm_user="root",
                       port=22, timeout=10):
        """
        Setup SSH passwordless access between remote host
        and VM, which is on the remote host.
        """
        pri_key = '~/.ssh/id_rsa'
        pub_key = '~/.ssh/id_rsa.pub'
        # Check the private key and public key file on remote host.
        cmd = "ls %s %s" % (pri_key, pub_key)
        result = self.runner.run(cmd, ignore_status=True)
        if result.exit_status:
            logging.debug("Create new SSH key pair")
            self.runner.run("ssh-keygen -t rsa -q -N '' -f %s" % pri_key)
        else:
            logging.info("SSH key pair already exist")
        session = self.runner.session
        # To avoid the host key checking
        ssh_options = "%s %s" % ("-o UserKnownHostsFile=/dev/null",
                                 "-o StrictHostKeyChecking=no")
        session.sendline("ssh-copy-id %s -i %s root@%s"
                         % (ssh_options, pub_key, vm_ip))
        while True:
            matched_strs = [r"[Aa]re you sure", r"[Pp]assword:\s*$",
                            r"lost connection", r"]#"]
            try:
                index, text = session.read_until_last_line_matches(
                    matched_strs, timeout=20,
                    internal_timeout=0.5)
            except (aexpect.ExpectTimeoutError,
                    aexpect.ExpectProcessTerminatedError), e:
                raise exceptions.TestFail(
                    "Setup autologin to vm failed:%s" % e)
            logging.debug("%s:%s", index, text)
            if index == 0:
                logging.debug("Sending 'yes' for fingerprint...")
                session.sendline("yes")
                continue
            elif index == 1:
                logging.debug("Sending '%s' for vm logging...", vm_pwd)
                session.sendline(vm_pwd)
                continue
            elif index == 2:
                raise exceptions.TestFail("Disconnected to vm on remote host.")
            elif index == 3:
                logging.debug("Logged in now...")
                break

    def check_network(self, vm_ip, count=5, timeout=60):
        """
        Check VM network connectivity
        """
        logging.debug("Check VM network connectivity...")
        vm_net_connectivity = False
        sleep_time = 5
        result = ""
        cmd = "ping -c %s %s" % (count, vm_ip)
        while timeout > 0:
            result = self.runner.run(cmd, ignore_status=True)
            if result.exit_status:
                time.sleep(sleep_time)
                timeout -= sleep_time
                continue
            else:
                vm_net_connectivity = True
                logging.info(result.stdout)
                break

        if not vm_net_connectivity:
            raise exceptions.TestFail("Failed to ping %s: %s" % (vm_ip,
                                                                 result.stdout))

    def run_command(self, vm_ip, command, vm_user="root", runner=None,
                    ignore_status=False):
        """
        Run command in the VM.

        :param vm_ip: The IP address of the VM
        :param command: The command to be executed in the VM
        :param vm_user: The logon user to the VM
        :param runner: The runner to execute the command
        :param ignore_status: True, not raise an exception and
            will return CmdResult object. False, raise an exception.

        :raise: exceptions.TestFail, if the command fails
        :return: CmdResult object
        """
        ssh_options = "%s %s" % ("-o UserKnownHostsFile=/dev/null",
                                 "-o StrictHostKeyChecking=no")
        cmd = 'ssh %s %s@%s "%s"' % (ssh_options, vm_user, vm_ip, command)
        ret = None
        try:
            ret = self.runner.run(cmd, ignore_status=ignore_status)
        except process.CmdError, detail:
            logging.debug("Failed to run '%s' in the VM: %s", cmd, detail)
            raise exceptions.TestFail("Failed to run '%s' in the VM: %s",
                                      cmd, detail)
        return ret


def canonicalize_disk_address(disk_address):
    """
    Canonicalize disk address.
    Convert {decimal|octal|hexadecimal} to decimal
    pci:0x0000.0x00.0x0b.0x0 => pci:0.0.11.0
    ide:00.00.00 => ide:0.0.0
    scsi:00.00.0x11 => scsi:0.0.17
    """
    add_info = disk_address.split(":")
    add_bus_type = add_info[0]
    add_detail = add_info[-1]
    add_detail_str = ""
    for add_item in add_detail.split("."):
        add_detail_str += ("%s." % int(add_item, 0))
    add_detail_str = "%s:%s" % (add_bus_type, add_detail_str[:-1])

    return add_detail_str
