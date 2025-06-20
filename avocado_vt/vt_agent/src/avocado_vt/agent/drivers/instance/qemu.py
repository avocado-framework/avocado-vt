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

"""
QEMU Virtual Machine Instance Driver

This module provides the QemuInstanceDriver class for managing QEMU virtual machine
instances within the Avocado-VT framework. It implements comprehensive VM lifecycle
management including creation, startup, shutdown, device management, and migration
support.

Key Features:
- VM instance lifecycle management (start, stop, pause, resume)
- Device hot-plug and hot-unplug operations
- Migration support with incoming migration capabilities
- Capability probing for QEMU features and migration parameters  
- Serial console and monitor connection management
- Process and resource cleanup

Classes:
- VMMigrateProtoUnsupportedError: Exception for unsupported migration protocols
- QemuInstanceInfo: Data class extending InstanceInfo with QEMU-specific fields
- QemuInstanceDriver: Main driver class for QEMU instance management

The driver supports various QEMU features including:
- Block devices and storage management
- Network device configuration
- Memory and CPU topology
- Security features (SEV, TDX)
- Device controllers and buses
- Graphics and input devices
- Serial consoles and debugging
"""

import copy
import json
import logging
import os
import re
from dataclasses import dataclass, field
from functools import partial

from avocado_vt.agent.core import data_dir as core_data_dir
from avocado_vt.agent.drivers.instance import InstanceDriver, InstanceInfo
from avocado_vt.agent.drivers.instance.utils import qemu_devices
from avocado_vt.agent.managers import connect_mgr, console_mgr
from virttest import data_dir, utils_misc, utils_qemu, virt_vm
from virttest.qemu_capabilities import Flags
from virttest.qemu_devices import qcontainer, qdevices
from virttest.qemu_devices.qdevice_format import qdevice_format
from virttest.qemu_devices.utils import (
    DeviceError,
    DeviceHotplugError,
    DeviceUnplugError,
    set_cmdline_format_by_cfg,
)
from virttest.utils_version import VersionInterval

import aexpect
from avocado.utils import distro, process

LOG = logging.getLogger("avocado.service." + __name__)

PARAMETERS_MAPPING = {
    "COMPRESS_LEVEL": {
        "options": ("compress-level",),
        "source_party": True,
        "destination_party": True,
    },
    "COMPRESS_THREADS": {
        "options": ("compress-threads",),
        "source_party": True,
        "destination_party": True,
    },
    "DECOMPRESS_THREADS": {
        "options": ("decompress-threads",),
        "source_party": True,
        "destination_party": True,
    },
    "THROTTLE_INITIAL": {
        "options": ("cpu-throttle-initial",),
        "source_party": True,
        "destination_party": False,
    },
    "THROTTLE_INCREMENT": {
        "options": ("cpu-throttle-increment",),
        "source_party": True,
        "destination_party": False,
    },
    "TLS_HOSTNAME": {
        "options": ("tls-hostname",),
        "source_party": True,
        "destination_party": False,
    },
    "XBZRLE_CACHE_SIZE": {
        "options": ("xbzrle-cache-size",),
        "source_party": True,
        "destination_party": True,
    },
    "MAX_POSTCOPY_BANDWIDTH": {
        "options": ("max-postcopy-bandwidth",),
        "source_party": True,
        "destination_party": True,
    },
    "MULTIFD_CHANNELS": {
        "options": ("multifd-channels",),
        "source_party": True,
        "destination_party": True,
    },
    "MULTIFD_ZLIB_LEVEL": {
        "options": ("multifd-zlib-level",),
        "source_party": True,
        "destination_party": True,
    },
    "MULTIFD_ZSTD_LEVEL": {
        "options": ("multifd-zstd-level",),
        "source_party": True,
        "destination_party": True,
    },
}


class VMMigrateProtoUnsupportedError(virt_vm.VMMigrateProtoUnknownError):
    """
    When QEMU tells us it doesn't know about a given migration protocol.

    This usually happens when we're testing older QEMU. It makes sense to
    skip the test in this situation.
    """

    def __init__(self, protocol=None, output=None):
        self.protocol = protocol
        self.output = output

    def __str__(self):
        return (
            "QEMU reports it doesn't know migration protocol '%s'. "
            "QEMU output: %s" % (self.protocol, self.output)
        )


@dataclass
class QemuInstanceInfo(InstanceInfo):
    spec_devs: list = field(default_factory=list)


class QemuInstanceDriver(InstanceDriver):
    BLOCKDEV_VERSION_SCOPE = "[2.12.0, )"
    SMP_DIES_VERSION_SCOPE = "[4.1.0, )"
    SMP_CLUSTERS_VERSION_SCOPE = "[7.0.0, )"
    SMP_BOOKS_VERSION_SCOPE = "[8.2.0, )"
    SMP_DRAWERS_VERSION_SCOPE = "[8.2.0, )"
    FLOPPY_DEVICE_VERSION_SCOPE = "[5.1.0, )"
    BLOCKJOB_BACKING_MASK_PROTOCOL_VERSION_SCOPE = "[9.0.0, )"

    MIGRATION_DOWNTIME_LIMTT_VERSION_SCOPE = "[5.1.0, )"
    MIGRATION_MAX_BANDWIDTH_VERSION_SCOPE = "[5.1.0, )"
    MIGRATION_XBZRLE_CACHE_SIZE_VERSION_SCOPE = "[5.1.0, )"

    def __init__(self, instance_id, instance_info):
        super(QemuInstanceDriver, self).__init__(instance_id, "qemu", instance_info)
        self._monitors = connect_mgr.get_connects_by_instance(self._instance_id)

        def get_hmp_cmds(qemu_binary):
            """:return: list of human monitor commands"""
            _ = process.run(
                "echo -e 'help\nquit' | %s -monitor "
                "stdio -vnc none -S" % qemu_binary,
                timeout=10,
                ignore_status=True,
                shell=True,
                verbose=False,
            ).stdout_text
            _ = re.findall(r"^([^()\|\[\sA-Z]+\|?\w+)", _, re.M)
            hmp_cmds = []
            for cmd in _:
                if "|" not in cmd:
                    if cmd != "The":
                        hmp_cmds.append(cmd)
                else:
                    hmp_cmds.extend(cmd.split("|"))
            return hmp_cmds

        def get_qmp_cmds(qemu_binary, workaround_qemu_qmp_crash=False):
            """:return: list of qmp commands"""
            cmds = None
            if not workaround_qemu_qmp_crash:
                cmds = process.run(
                    "echo -e '"
                    '{ "execute": "qmp_capabilities" }\n'
                    '{ "execute": "query-commands", "id": "RAND91" }\n'
                    '{ "execute": "quit" }\''
                    "| %s -qmp stdio -vnc none -S | grep return |"
                    " grep RAND91" % qemu_binary,
                    timeout=10,
                    ignore_status=True,
                    shell=True,
                    verbose=False,
                ).stdout_text.splitlines()
            if not cmds:
                # Some qemu versions crashes when qmp used too early; add sleep
                cmds = process.run(
                    "echo -e '"
                    '{ "execute": "qmp_capabilities" }\n'
                    '{ "execute": "query-commands", "id": "RAND91" }\n'
                    '{ "execute": "quit" }\' | (sleep 1; cat )'
                    "| %s -qmp stdio -vnc none -S | grep return |"
                    " grep RAND91" % qemu_binary,
                    timeout=10,
                    ignore_status=True,
                    shell=True,
                    verbose=False,
                ).stdout_text.splitlines()
            if cmds:
                cmds = re.findall(r'{\s*"name"\s*:\s*"([^"]+)"\s*}', cmds[0])
            if cmds:  # If no mathes, return None
                return cmds

        workaround_qemu_qmp_crash = "always"
        self._migrate_inc_uri = None
        self._pass_fds = []
        self.__qemu_binary = "/usr/libexec/qemu-kvm"
        self.__execute_qemu_last = None
        self.__execute_qemu_out = ""
        # Check whether we need to add machine_type
        cmd = (
            "echo -e 'quit' | %s -monitor stdio -nodefaults -nographic -S"
            % self.__qemu_binary
        )
        result = process.run(
            cmd, timeout=10, ignore_status=True, shell=True, verbose=False
        )
        # Some architectures (arm) require machine type to be always set and some
        # hardware/firmware restrictions cause we need to set machine type.
        failed_pattern = (
            r"(?:kvm_init_vcpu.*failed)|(?:machine specified)"
            r"|(?:appending -machine)"
        )
        output = result.stdout_text + result.stderr_text
        if result.exit_status and re.search(failed_pattern, output):
            self.__workaround_machine_type = True
            basic_qemu_cmd = "%s -machine none" % self.__qemu_binary
        else:
            self.__workaround_machine_type = False
            basic_qemu_cmd = self.__qemu_binary
        self.__qemu_help = self._execute_qemu("-help", 10)
        # escape the '?' otherwise it will fail if we have a single-char
        # filename in cwd
        self.__device_help = self._execute_qemu("-device \? 2>&1", 10)
        self.__object_help = self._execute_qemu("-object \? 2>&1", 10)
        self.__machines_info = utils_qemu.get_machines_info(self.__qemu_binary)
        self.__qemu_ver = utils_qemu.get_qemu_version(self.__qemu_binary)[0]
        self.__hmp_cmds = get_hmp_cmds(basic_qemu_cmd)
        self.__qmp_cmds = get_qmp_cmds(
            basic_qemu_cmd, workaround_qemu_qmp_crash == "always"
        )

    @property
    def monitor(self):
        if not self._monitors:
            self._monitors = connect_mgr.get_connects_by_instance(self._instance_id)
        return self._monitors[0] if self._monitors else None

    def _has_hmp_cmd(self, cmd):
        """
        :param cmd: Desired command
        :return: Is the desired command supported by this qemu's human monitor?
        """
        return cmd in self.__hmp_cmds

    def _has_qmp_cmd(self, cmd):
        """
        :param cmd: Desired command
        :return: Is the desired command supported by this qemu's QMP monitor?
        """
        return cmd in self.__qmp_cmds

    def _execute_qemu(self, options, timeout=5):
        """
        Execute this qemu and return the stdout+stderr output.
        :param options: additional qemu options
        :type options: string
        :param timeout: execution timeout
        :type timeout: int
        :return: Output of the qemu
        :rtype: string
        """
        if self.__execute_qemu_last != options:
            if self.__workaround_machine_type:
                cmd = "%s -machine none %s 2>&1" % (self.__qemu_binary, options)
            else:
                cmd = "%s %s 2>&1" % (self.__qemu_binary, options)
            result = process.run(
                cmd, timeout=timeout, ignore_status=True, shell=True, verbose=False
            )
            self.__execute_qemu_out = result.stdout_text
            self.__execute_qemu_last = options
        return self.__execute_qemu_out

    def _has_option(self, option):
        """
        :param option: Desired option
        :return: Is the desired option supported by current qemu?
        """
        return bool(re.search(r"^-%s(\s|$)" % option, self.__qemu_help, re.MULTILINE))

    def _has_device(self, device):
        """
        :param device: Desired device
        :return: Is the desired device supported by current qemu?
        """
        return bool(
            re.search(r'name "%s"|alias "%s"' % (device, device), self.__device_help)
        )

    def _has_object(self, obj):
        """
        :param obj: Desired object string, e.g. 'sev-guest'
        :return: True if the object is supported by qemu, or False
        """
        return bool(re.search(r"^\s*%s\n" % obj, self.__object_help, re.M))

    def _qemu_proc_term_handler(self):
        """Monitors qemu process unexpected exit.

        Callback function to detect QEMU process non-zero exit status and
        push VMExitStatusError to background error bus.
        """
        devices = self.instance_info.devices
        for snapshot in devices.temporary_image_snapshots:
            try:
                os.unlink(snapshot)
            except OSError:
                pass
        devices.temporary_image_snapshots.clear()

    def _start_daemons(self):
        """Start the daemons of qemu device."""
        if self.instance_info.devices:
            for dev in self.instance_info.devices:
                if isinstance(dev, qdevices.QDaemonDev):
                    dev.start_daemon()

    def start(self, cmdline, timeout=60):
        """
        Start the QEMU virtual machine instance.

        This method starts the QEMU process with the provided command line,
        performs various validation checks, and handles potential startup errors
        including KVM initialization, hugepage allocation, and migration protocol issues.

        :param cmdline: The complete QEMU command line to execute
        :type cmdline: str
        :param timeout: Timeout in seconds for the startup process
        :type timeout: int
        :return: The running QEMU process object
        :rtype: aexpect.Expect
        :raises VMStartError: If QEMU process becomes defunct
        :raises VMCreateError: If QEMU process fails to start
        :raises VMMigrateProtoUnsupportedError: If migration protocol is unsupported
        :raises VMKVMInitError: If KVM initialization fails
        :raises VMHugePageError: If hugepage allocation fails
        """
        self._start_daemons()
        LOG.info(
            "<Instance: %s> Running qemu command (reformatted):\n%s",
            self._instance_id,
            "<Instance: %s>    -" % self._instance_id
            + cmdline.replace(" -", " \\\n<Instance: %s>    -" % self._instance_id),
        )
        process = aexpect.run_tail(
            command=cmdline,
            termination_func=partial(self._qemu_proc_term_handler, False),
            output_func=LOG.info,
            output_prefix="<Instance: %s> [qemu output] " % self._instance_id,
            auto_close=False,
            pass_fds=self._pass_fds,
        )

        LOG.info(
            "<Instance: %s> Created qemu process with parent PID %d",
            self._instance_id,
            process.get_pid(),
        )

        # Make sure qemu is not defunct
        if process.is_defunct():
            LOG.error("Bad things happened, qemu process is defunct")
            err = "Qemu is defunct.\nQemu output:\n%s" % process.get_output()
            raise virt_vm.VMStartError(self._instance_id, err)

        # Make sure the process was started successfully
        if not process.is_alive():
            status = process.get_status()
            output = process.get_output().strip()
            migration_in_course = self._migrate_inc_uri is not None
            unknown_protocol = "unknown migration protocol" in output
            if migration_in_course and unknown_protocol:
                e = VMMigrateProtoUnsupportedError(self._migrate_inc_uri, output)
            else:
                e = virt_vm.VMCreateError(cmdline, status, output)
            raise e

        # Get the output so far, to see if we have any problems with
        # KVM modules or with hugepage setup.
        output = process.get_output()

        if re.search("Could not initialize KVM", output, re.IGNORECASE):
            e = virt_vm.VMKVMInitError(cmdline, process.get_output())
            raise e

        if "alloc_mem_area" in output:
            e = virt_vm.VMHugePageError(cmdline, process.get_output())
            raise e

        LOG.debug(
            "<Instance: %s> Instance appears to be alive with PID %s",
            self._instance_id,
            self.get_pid(process),
        )
        return process

    def _stop_daemons(self):
        """Stop the daemons of qemu device."""
        if self.instance_info.devices:
            for dev in self.instance_info.devices:
                if isinstance(dev, qdevices.QDaemonDev):
                    try:
                        dev.stop_daemon()
                    except DeviceError as err:
                        LOG.error("Failed to stop daemon: %s", err)

    def is_dead(self):
        """
        Return True if the qemu process is dead.
        """
        return (
            not self.instance_info.process or not self.instance_info.process.is_alive()
        )

    def _wait_until_paused(self, timeout):
        """
        Wait until the VM is paused.

        :param timeout: Timeout in seconds.
        :return: True in case the VM is paused before timeout, otherwise
                 return None.
        """
        return self._wait_for_status("paused", timeout)

    def _wait_until_dead(self, timeout, first=0.0, step=1.0):
        """
        Wait until VM is dead.

        :param timeout: Timeout in seconds
        :param first: Time to sleep before first attempt
        :param steps: Time to sleep between attempts in seconds
        :return: True if VM is dead before timeout, otherwise returns None.
        """
        return utils_misc.wait_for(self.is_dead, timeout, first, step)

    def _serial_login(self, username=None, password=None, prompt=None, timeout=60):
        """
        Perform login via serial console connection.

        This method establishes a login session through the VM's serial console
        by handling authentication prompts and returning the active console session.

        :param username: Username for login authentication
        :type username: str or None
        :param password: Password for login authentication
        :type password: str or None
        :param prompt: Expected shell prompt after successful login
        :type prompt: str or None
        :param timeout: Maximum time to wait for login completion
        :type timeout: int
        :return: The active serial console session
        :rtype: Console object
        :raises ValueError: If no consoles are available for the instance
        """
        consoles = console_mgr.get_consoles_by_instance(self._instance_id, "serial")
        if not consoles:
            raise ValueError(f"No consoles found for instance {self._instance_id}")
        serial = consoles[0]
        aexpect.remote.handle_prompts(serial, username, password, prompt, timeout)
        return serial

    def _graceful_shutdown(
        self, shutdown_cmd=None, username=None, password=None, prompt=None, timeout=60
    ):
        """
        Try to gracefully shut down the VM.

        :return: True if VM was successfully shut down, None otherwise.

        Note that the VM is not necessarily dead when this function returns
        True. If QEMU is running in -no-shutdown mode, the QEMU process
        may be still alive.
        """

        def _shutdown_by_sendline():
            try:
                session.sendline(shutdown_cmd)
                if self._wait_until_dead(timeout, 1, 1):
                    return True
            finally:
                session.close()

        if shutdown_cmd:
            # Try to destroy with shell command
            LOG.debug("Shutting down instance %s (shell)", self._instance_id)
            try:
                # FIXME: Login via serial mandatory
                session = self._serial_login(username, password, prompt, timeout)
            except (IndexError) as e:
                try:
                    session = self._serial_login(username, password, prompt, timeout)
                except (aexpect.remote.LoginError, virt_vm.VMError) as e:
                    LOG.debug(e)
                else:
                    # Successfully get session by serial_login()
                    _shutdown_by_sendline()
            except (aexpect.remote.LoginError, virt_vm.VMError) as e:
                LOG.debug(e)
            except ValueError as e:
                LOG.error(e)
            else:
                # There is no exception occurs
                _shutdown_by_sendline()

    def stop(
        self,
        graceful=True,
        timeout=60,
        shutdown_cmd=None,
        username=None,
        password=None,
        prompt=None,
    ):
        """
        Stop the QEMU virtual machine instance.

        This method attempts to stop the VM using a multi-step approach:
        1. If graceful=True, attempts graceful shutdown via shell command
        2. If that fails, tries to quit via monitor command
        3. As a last resort, forcefully kills the process tree

        :param graceful: Whether to attempt graceful shutdown first
        :type graceful: bool
        :param timeout: Maximum time to wait for shutdown operations
        :type timeout: int
        :param shutdown_cmd: Shell command to execute for graceful shutdown
        :type shutdown_cmd: str or None
        :param username: Username for serial console login (if needed)
        :type username: str or None
        :param password: Password for serial console login (if needed)
        :type password: str or None
        :param prompt: Expected shell prompt for serial console login
        :type prompt: str or None
        """
        try:
            # Is it already dead?
            if self.is_dead():
                return

            LOG.debug(
                "Destroying the instance %s (PID %s)", self._instance_id, self.get_pid()
            )
            if graceful:
                self._graceful_shutdown(
                    shutdown_cmd, username, password, prompt, timeout
                )
                if self.is_dead():
                    LOG.debug("Instance %s down (shell)", self._instance_id)
                    return
                else:
                    LOG.debug(
                        "Instance %s failed to go down (shell)", self._instance_id
                    )

            if self.monitor:
                # Try to finish process with a monitor command
                LOG.debug("Ending the instance %s process (monitor)", self._instance_id)
                try:
                    self.monitor.quit()
                except Exception as e:
                    LOG.warn(e)
                    if self.is_dead():
                        LOG.warn(
                            "Instance %s down during try to kill it by monitor",
                            self._instance_id,
                        )
                        return
                else:
                    # Wait for the VM to be really dead
                    if self._wait_until_dead(5, 0.5, 0.5):
                        LOG.debug("Instance %s down (monitor)", self._instance_id)
                        return
                    else:
                        LOG.debug(
                            "Instance %s failed to go down (monitor)", self._instance_id
                        )

            # If the VM isn't dead yet...
            pid = self.instance_info.process.get_pid()
            LOG.debug(
                "Ending Instance %s process (killing PID %s)", self._instance_id, pid
            )
            try:
                utils_misc.kill_process_tree(pid, 9, timeout=60)
                LOG.debug("Instance %s down (process killed)", self._instance_id)
            except RuntimeError:
                # If all else fails, we've got a zombie...
                LOG.error(
                    "Instance %s (PID %s) is a zombie!",
                    self._instance_id,
                    self.instance_info.process.get_pid(),
                )
        finally:
            self._stop_daemons()

    def _cleanup_serial_console(self):
        """
        Close serial console and associated log file
        """
        consoles = console_mgr.get_consoles_by_instance(self._instance_id, "serial")
        for console in consoles:
            console.close()

    def cleanup(self, free_mac_addresses=True):
        """
        Clean up resources associated with the QEMU instance.

        This method performs cleanup operations including closing monitor
        connections, closing the QEMU process, and removing temporary files
        such as monitor sockets and console connection files.

        :param free_mac_addresses: Whether to free MAC addresses
        :type free_mac_addresses: bool
        """
        monitor_files = []
        for monitor in self._monitors:
            try:
                monitor_files.append(monitor.address)
                monitor.close()
            except Exception:
                pass

        if self.instance_info.process:
            self.instance_info.process.close()

        # Generate the tmp file which should be deleted.
        file_list = []
        file_list += monitor_files
        file_list += [
            console.filename
            for console in console_mgr.get_consoles_by_instance(self._instance_id)
        ]

        for f in file_list:
            try:
                if f:
                    os.unlink(f)
            except OSError:
                pass

    def get_process_info(self, attr):
        """
        Get information about the QEMU process.

        This method retrieves various information about the running QEMU process
        such as process ID, status, output, and state information.

        :param attr: The attribute of information to retrieve ("pid", "status",
                     "output", "alive", "defunct")
        :type attr: str
        :return: The requested process information
        :rtype: varies (int for pid, bool for alive/defunct, str for status/output)
        :raises ValueError: If info_name is unknown or no process is available
        """
        if self.instance_info.process:
            process = self.instance_info.process
            if attr == "pid":
                return process.get_pid()
            elif attr == "status":
                return process.get_status()
            elif attr == "output":
                return process.get_output()
            elif attr == "alive":
                return process.is_alive()
            elif attr == "defunct":
                return process.is_defunct()
            else:
                raise ValueError(f"Unknown attribute {attr}")
        else:
            raise ValueError(
                f"No available process for VM instance {self.instance_info.uuid}"
            )

    def get_serial_info(self, serial_id, attr):
        """
        Get attribute information about a serial console connection.

        This method retrieves attribute information about a specific serial
        console connection by its ID.

        :param serial_id: The ID of the serial console
        :type serial_id: str
        :param attr: The attribute of information to retrieve
        :type attr: str
        :return: The requested serial console information
        :rtype: varies
        :raises ValueError: If serial_id is unknown or no serials are available
        """
        if self.instance_info.serials:
            serial_info = self.instance_info.serials.get(serial_id)
            if serial_info:
                return serial_info.get(attr)
            else:
                raise ValueError(f"Unknown serial {serial_id}")
        else:
            raise ValueError(
                f"No available serials for VM instance {self.instance_info.uuid}"
            )

    def get_pid(self, parent_process=None):
        """
        Get the PID of the QEMU child process.

        This method finds the actual QEMU process PID by looking for child
        processes of the parent process using the ps command.

        :param parent_process: The parent process object to search from
        :type parent_process: Process or None
        :return: The PID of the QEMU process, or None if not found
        :rtype: int or None
        """
        if not parent_process:
            parent_process = self.instance_info.process
        try:
            cmd = "ps --ppid=%d -o pid=" % parent_process.get_pid()
            children = process.run(
                cmd, verbose=False, ignore_status=True
            ).stdout_text.split()
            return int(children[0])
        except (TypeError, IndexError, ValueError):
            return None

    def _get_pci_parent_bus(self, bus):
        """
        Get the parent bus configuration for PCI devices.

        This method creates the parent bus configuration dictionary
        for PCI device attachment.

        :param bus: The bus identifier
        :type bus: str or None
        :return: Parent bus configuration dictionary or None
        :rtype: dict or None
        """
        if bus:
            parent_bus = {"aobject": bus}
        else:
            parent_bus = None
        return parent_bus

    def _get_cmdline_format_cfg(self):
        """
        get data from file or input from parameter and then convert data to dict

        :return: style data in dict
        """

        def _file(filepath):
            if not filepath:
                raise ValueError("The filepath is empty!")
            if not os.path.isabs(filepath):
                filepath = data_dir.get_backend_cfg_path("qemu", filepath)
            with open(filepath, "r") as f:
                content = f.read()
            return content

        def _string(content):
            return content

        def _default(dummy):
            return "{}"

        # FIXME: List the qemu format mapping here
        os_distro = distro.detect()
        os_name = os_distro.name
        os_version = os_distro.version
        os_release = os_distro.release
        qemu_format_os_distro_mapping = {
            "rhel.9.6": "libvirt.9.0+.json",
            "rhel.9.5": "libvirt.9.0+.json",
            "rhel.9.4": "libvirt.9.0+.json",
            "rhel.9.3": "libvirt.9.0+.json",
            "rhel.9.2": "libvirt.9.0+.json",
            "rhel.9.1": "libvirt.8.5.json",
            "rhel.9.0": "libvirt.8.3.json",
            "rhel.8.10": "libvirt.8.0.json",
            "rhel.8.9": "libvirt.8.0.json",
            "rhel.8.8": "libvirt.8.0.json",
            "rhel.8.7": "libvirt.8.0.json",
            "rhel.8.6": "libvirt.8.0.json",
        }
        libvirt_json = qemu_format_os_distro_mapping.get(
            f"{os_name}.{os_version}.{os_release}", "libvirt-latest.json"
        )
        json_file = os.path.join(
            core_data_dir.get_data_dir(), "qemu_cmdline_format", libvirt_json
        )
        self._params["qemu_cmdline_format_cfg"] = f"file:{json_file}"
        handler, value = self._params.get("qemu_cmdline_format_cfg", ":").split(":", 1)
        get_func = {"file": _file, "string": _string, "": _default}
        if handler not in get_func:
            LOG.warning("Unknown qemu cmdline format config...ignoring!")
            handler, value = "", ""
        return json.loads(get_func.get(handler)(value))

    def probe_capabilities(self):
        """
        Probe and return all supported QEMU capabilities.

        This method combines results from hardware capabilities and migration
        parameters to provide a complete set of supported QEMU features.

        :return: Set of supported capability strings
        :rtype: set
        """
        caps = set()
        for cap in self._probe_capabilities():
            caps.add(cap)

        for cap in self._probe_migration_parameters():
            caps.add(cap)

        return caps

    def _probe_capabilities(self):
        """
        Probe QEMU hardware and feature capabilities.

        This method checks QEMU version and available options to determine
        supported features like blockdev, SMP topology, security features,
        and device capabilities.

        :return: List of supported capability strings
        :rtype: list
        """
        caps = []
        # -blockdev
        if self._has_option("blockdev") and self.__qemu_ver in VersionInterval(
            self.BLOCKDEV_VERSION_SCOPE
        ):
            caps.append("BLOCKDEV")
        # -smp dies=?
        if self.__qemu_ver in VersionInterval(self.SMP_DIES_VERSION_SCOPE):
            caps.append("SMP_DIES")
        # -smp clusters=?
        if self.__qemu_ver in VersionInterval(self.SMP_CLUSTERS_VERSION_SCOPE):
            caps.append("SMP_CLUSTERS")
        # -smp drawers=?
        if self.__qemu_ver in VersionInterval(self.SMP_DRAWERS_VERSION_SCOPE):
            caps.append("SMP_DRAWERS")
        # -smp book=?
        if self.__qemu_ver in VersionInterval(self.SMP_BOOKS_VERSION_SCOPE):
            caps.append("SMP_BOOKS")
        # -incoming defer
        if self._has_option("incoming defer"):
            caps.append("INCOMING_DEFER")
        # -machine memory-backend
        machine_help = self._execute_qemu("-machine none,help")
        if re.search(r"memory-backend=", machine_help, re.MULTILINE):
            caps.append("MACHINE_MEMORY_BACKEND")
        # -object sev-guest
        if self._has_object("sev-guest"):
            caps.append("SEV_GUEST")
        # -object tdx-guest
        if self._has_object("tdx-guest"):
            caps.append("TDX_GUEST")
        # -device floppy,drive=$drive
        if self.__qemu_ver in VersionInterval(self.FLOPPY_DEVICE_VERSION_SCOPE):
            caps.append("FLOPPY_DEVICE")

        # QMP: block-stream/block-commit @backing-mask-protocol
        # TODO: probe cap via using the qmp command `query-qmp-schema`
        #       instead of hardcoding the version range
        if self.__qemu_ver in VersionInterval(
            self.BLOCKJOB_BACKING_MASK_PROTOCOL_VERSION_SCOPE
        ):
            caps.append("BLOCKJOB_BACKING_MASK_PROTOCOL")

        if self._has_qmp_cmd("migrate-set-parameters") and self._has_hmp_cmd(
            "migrate_set_parameter"
        ):
            caps.append("MIGRATION_PARAMS")
        return caps

    def _probe_migration_parameters(self):
        """Probe migration parameters."""
        params = []
        mig_params_mapping = {
            "DOWNTIME_LIMIT": self.MIGRATION_DOWNTIME_LIMTT_VERSION_SCOPE,
            "MAX_BANDWIDTH": self.MIGRATION_MAX_BANDWIDTH_VERSION_SCOPE,
            "XBZRLE_CACHE_SIZE": self.MIGRATION_XBZRLE_CACHE_SIZE_VERSION_SCOPE,
        }

        for mig_param, ver_scope in mig_params_mapping.items():
            if self.__qemu_ver in VersionInterval(ver_scope):
                params.append(mig_param)

        return params

    def _create_devices(self, spec):
        """
        Create and configure all QEMU devices based on the provided specification.

        This method builds a complete device container with all QEMU devices
        including machine configuration, controllers, storage devices, network
        devices, and various peripherals based on the instance specification.

        :param spec: Complete device specification dictionary containing all
                     device configurations for the VM instance
        :type spec: dict
        :return: Container with all configured QEMU devices ready for command line generation
        :rtype: qcontainer.DevContainer
        """
        self._params = copy.deepcopy(spec)
        self._format_cfg = self._get_cmdline_format_cfg()
        qdevice_format.qemu_binary = self.__qemu_binary
        devices = qcontainer.DevContainer(self.__qemu_binary, self._params["name"])

        cmd = ""
        devices.insert(qdevices.QStringDevice("PREFIX", cmdline=cmd))
        devices.insert(qdevices.QStringDevice("qemu", cmdline=self.__qemu_binary))

        if self._params["preconfig"]:
            devices.insert(qdevices.QStringDevice("preconfig", cmdline="--preconfig"))

        name = self._params["name"]
        devices.insert(qdevices.QStringDevice("vmname", cmdline=f"-name {name}"))

        sandbox = self._params.get("sandbox")
        if sandbox:
            dev = qemu_devices.sandbox.create_sandbox_device(sandbox)
            devices.insert(dev)

        firmware = self._params.get("firmware")
        devs = qemu_devices.firmware.create_firmware_devices(firmware)
        devices.insert(devs)

        machine = self._params.get("machine")
        if machine:
            cpu = self._params["cpu"]
            controller = self._params["controllers"][0]
            devs = qemu_devices.machine.create_machine_devices(
                machine,
                cpu,
                controller,
                devices.has_option("device"),
                devices.has_option("global"),
            )
            devices.insert(devs)

        controllers = self._params.get("controllers")
        if controllers:
            extra_pcie = []
            for controller in controllers:
                controller_type = controller.get("type")
                if controller_type in (
                    "pcie-root-port",
                    "ioh3420",
                    "x3130-upstream",
                    "x3130",
                    "pci-bridge",
                    "i82801b11-bridge",
                    "pcie-pci-bridge",
                ):
                    name = controller.get("id")
                    # FIXME: workaround to distinguish the extra pci root port
                    if not name.startswith("pcie_extra_root_port_"):
                        devs = (
                            qemu_devices.controller_pci.create_pci_controller_devices(
                                controller, self._format_cfg
                            )
                        )
                        devices.insert(devs)
                    else:
                        extra_pcie.append(controller)

                    func_0_addr = None
                    extra_port_num = len(extra_pcie)
                    for num, pci_controller in enumerate(extra_pcie):
                        try:
                            root_port = qemu_devices.controller_pci.create_pci_controller_devices(
                                pci_controller, self._format_cfg
                            )
                            func_num = num % 8
                            if func_num == 0:
                                devices.insert(root_port)
                                func_0_addr = root_port.get_param("addr")
                            else:
                                port_addr = "%s.%s" % (func_0_addr, hex(func_num))
                                root_port.set_param("addr", port_addr)
                                devices.insert(root_port)
                        except DeviceError:
                            LOG.warning(
                                "No sufficient free slot for extra"
                                " root port, discarding %d of them"
                                % (extra_port_num - num)
                            )
                            break
                elif controller_type in (
                    "piix3-usb-uhci",
                    "piix4-usb-uhci",
                    "usb-ehci",
                    "ich9-usb-ehci1",
                    "ich9-usb-uhci1",
                    "ich9-usb-uhci2",
                    "ich9-usb-uhci3",
                    "vt82c686b-usb-uhci",
                    "pci-ohci",
                    "nec-usb-xhci",
                    "qusb1",
                    "qusb2",
                    "qemu-xhci",
                ):
                    pci_bus = self._get_pci_parent_bus(controller["bus"])
                    devs = qemu_devices.controller_usb.create_usb_controller_devices(
                        controller, pci_bus, self._format_cfg
                    )
                    devices.insert(devs)

        launch_security = self._params.get("launch_security")
        if launch_security:
            dev = qemu_devices.launch_security.create_launch_security_device(
                launch_security
            )
            devices.insert(dev)

        defaults = self._params.get("defaults")
        if not defaults:
            dev = qdevices.QStringDevice("nodefaults", cmdline=" -nodefaults")
            devices.insert(dev)

        iommu = self._params.get("iommu")
        if iommu:
            parent_bus = self._get_pci_parent_bus(iommu.get("bus"))
            dev = qemu_devices.iommu.create_iommu_device(
                iommu, parent_bus, self._format_cfg
            )
            devices.insert(dev)

        vga = self._params.get("vga")
        if vga:
            parent_bus = self._get_pci_parent_bus(vga.get("bus"))
            dev = qemu_devices.vga.create_vga_device(vga, parent_bus, self._format_cfg)
            devices.insert(dev)

        watchdog = self._params.get("watchdog")
        if watchdog:
            parent_bus = self._get_pci_parent_bus(watchdog.get("bus"))
            devs = qemu_devices.watchdog.create_watchdog_devices(watchdog, parent_bus)
            devices.insert(devs)

        memory = self._params.get("memory")
        machine_dev = devices.get_by_properties({"type": "machine"})[0]
        if memory:
            devs = qemu_devices.memory.create_memory(memory, self._format_cfg)
            devices.insert(devs)
            if Flags.MACHINE_MEMORY_BACKEND in devices.caps and not self._params.get(
                "numa"
            ):
                for dev in devs:
                    if isinstance(dev, qdevices.Memory):
                        machine_dev.set_param("memory-backend", dev.get_qid())
                        break

            devs = qemu_devices.memory.create_memory_devices(memory, self._format_cfg)
            for mem_devs in memory.get("devices", []):
                spec_devs = {}
                spec_devs["spec"] = mem_devs
                spec_devs["devices"] = []
                mem_backend = mem_devs.get("backend")
                mem_id = mem_devs.get("id")
                for dev in devs:
                    if dev.get_qid() in (mem_backend.get("id"), mem_id):
                        spec_devs["devices"].append(dev)
                self.instance_info.spec_devs.append(spec_devs)
            devices.insert(devs)

        numa = self._params.get("numa")
        if numa:
            nodes = numa.get("nodes")
            if nodes:
                devs = qemu_devices.numa.create_numa_nodes(nodes)
                devices.insert(devs)

            dists = numa.get("dists")
            if dists:
                devs = qemu_devices.numa.create_numa_dists(dists)
                devices.insert(devs)

            cpus = numa.get("cpus")
            if cpus:
                devs = qemu_devices.numa.create_numa_cpus(cpus)
                devices.insert(devs)

            hmat_lbs = numa.get("hmat_lbs")
            if hmat_lbs:
                devs = qemu_devices.numa.create_numa_hmat_lbs(hmat_lbs)
                devices.insert(devs)

            hmat_caches = numa.get("hmat_caches")
            if hmat_caches:
                devs = qemu_devices.numa.create_numa_hmat_caches(hmat_caches)
                devices.insert(devs)

        cpu = self._params.get("cpu")
        if cpu:
            devs = qemu_devices.cpu.create_cpu_devices(cpu)
            devices.insert(devs)

        soundcards = self._params.get("soundcards")
        if soundcards:
            for soundcard in soundcards:
                parent_bus = self._get_pci_parent_bus(soundcard["bus"])
                devs = qemu_devices.soundcard.create_soundcard_devices(
                    soundcard, parent_bus, self._format_cfg
                )
                devices.insert(devs)

        monitors = self._params.get("monitors")
        if monitors:
            for monitor in monitors:
                devs = qemu_devices.monitor.create_monitor_devices(
                    monitor, devices.has_option("chardev"), self._format_cfg
                )
                devices.insert(devs)

        panics = self._params.get("panics")
        if panics:
            for panic in panics:
                parent_bus = self._get_pci_parent_bus(panic.get("bus"))
                dev = qemu_devices.panic.create_panic_device(
                    panic, parent_bus, self._format_cfg
                )
                devices.insert(dev)

        vmcoreinfo = self._params.get("vmcoreinfo")
        if vmcoreinfo:
            dev = qemu_devices.vmcoreinfo.create_vmcoreinfo()
            devices.insert(dev)

        serials = self._params.get("serials")
        if serials:
            count = 0
            for serial in serials:
                parent_bus = self._get_pci_parent_bus(serial.get("bus"))
                devs = qemu_devices.serial.create_serial_devices(
                    devices,
                    serial,
                    count,
                    parent_bus,
                    self._params["machine"]["type"],
                    self._params.get("os").get("arch"),
                    devices.has_option("chardev"),
                    devices.has_device(serial["type"]),
                    self._uuid,
                    len(self._params.get("serials")),
                )
                for dev in devs:
                    if isinstance(dev, qdevices.CharDevice):
                        self.instance_info.serials[serial["id"]] = {
                            "filename": dev.get_param("path")
                        }
                        break
                devices.insert(devs)
                count += 1

        rngs = self._params.get("rngs")
        if rngs:
            for rng in rngs:
                parent_bus = self._get_pci_parent_bus(rng.get("bus"))
                devs = qemu_devices.rng.create_rng_devices(devices, rng, parent_bus)
                devices.insert(devs)

        debugs = self._params.get("debugs")
        if debugs:
            for debug in debugs:
                parent_bus = self._get_pci_parent_bus(debug.get("bus"))
                machine_type = self._params["machine"]["type"]
                driver_id = self._uuid
                uuid = self._params["uuid"]
                instance_id = self._instance_id
                devs = qemu_devices.debug.create_debug_devices(
                    devices,
                    debug,
                    parent_bus,
                    machine_type,
                    driver_id,
                    uuid,
                    instance_id,
                )
                devices.insert(devs)

        usbs = self._params.get("usbs")
        if usbs:
            for usb in usbs:
                dev = qemu_devices.usb.create_usb_device(devices, usb, self._format_cfg)
                devices.insert(dev)

        iothreads = self._params.get("iothreads")
        if iothreads:
            for iothread in iothreads:
                dev = qemu_devices.iothread.create_iothread_device(iothread)
                devices.insert(dev)

        throttle_groups = self._params.get("throttle_groups")
        if throttle_groups:
            for throttle_group in throttle_groups:
                dev = qemu_devices.throttle_group.create_throttle_group_device(
                    throttle_group
                )
                devices.insert(dev)

        disks = self._params.get("disks")
        if disks:
            for disk in disks:
                parent_bus = self._get_pci_parent_bus(disk.get("bus"))
                devs = qemu_devices.disk.create_disk_devices(
                    devices, disk, parent_bus, self._format_cfg
                )
                self.instance_info.spec_devs.append({"spec": disk, "devices": devs})
                devices.insert(devs)

        filesystems = self._params.get("filesystems")
        if filesystems:
            for filesystem in filesystems:
                machine_type = self._params["machine"]["type"]
                sock_name = "-".join(
                    (self._params["name"], filesystem["id"], "virtiofsd.sock")
                )
                dev = qemu_devices.filesystem.create_filesystem_device(
                    filesystem, machine_type, sock_name
                )
                devices.insert(dev)

        nets = self._params.get("nets")
        if nets:
            for net in nets:
                parent_bus = self._get_pci_parent_bus(net.get("device").get("bus"))
                netdev_id = net.get("backend").get("id")
                sock_name = "-".join((self._params["name"], netdev_id, "passt.sock"))
                devs = qemu_devices.net.create_net_devices(
                    devices,
                    net,
                    parent_bus,
                    self._format_cfg,
                    sock_name,
                    self._pass_fds,
                )
                self.instance_info.spec_devs.append({"spec": net, "devices": devs})
                devices.insert(devs)

        vsocks = self._params.get("vsocks")
        if vsocks:
            for vsock in vsocks:
                dev = qemu_devices.vsock.create_vsock_device(vsock, self._format_cfg)
                devices.insert(dev)

        os = self._params.get("os")
        if os:
            machine_type = self._params["machine"]["type"]
            dev = qemu_devices.os.create_os_device(devices, os, machine_type)
            devices.insert(dev)

        graphics = self._params.get("graphics")
        if graphics:
            for graphics in graphics:
                dev = qemu_devices.graphic.create_graphics_device(devices, graphics)
                devices.insert(dev)

        rtc = self._params.get("rtc")
        if rtc:
            dev = qemu_devices.rtc.create_rtc_device(devices, rtc)
            devices.insert(dev)

        tpms = self._params.get("tpms")
        if tpms:
            for tpm in tpms:
                devs = qemu_devices.tpm.create_tpm_devices(
                    tpm, self._instance_id, self._format_cfg
                )
                devices.insert(devs)

        devices.insert(qdevices.QStringDevice("kvm", cmdline="-enable-kvm"))

        pm = self._params.get("power_management")
        if pm:
            if pm.get("no_shutdown"):
                if devices.has_option("no-shutdown"):
                    devices.insert(
                        qdevices.QStringDevice("noshutdown", cmdline="-no-shutdown")
                    )

        inputs = self._params.get("inputs")
        if inputs:
            for input in inputs:
                machine_type = self._params["machine"]["type"]
                dev = qemu_devices.input.create_input_device(
                    devices, input, machine_type
                )
                devices.insert(dev)

        balloons = self._params.get("balloons")
        if balloons:
            for balloon in balloons:
                machine_type = self._params["machine"]["type"]
                dev = qemu_devices.balloon.create_balloon_device(balloon, machine_type)
                devices.insert(dev)

        keyboard_layout = self._params.get("keyboard_layout")
        if keyboard_layout:
            dev = qdevices.QStringDevice("k", cmdline=keyboard_layout)
            devices.insert(dev)

        for dev in devices:
            if dev.get_param("driver", "") in (
                "pcie-root-port",
                "pcie-pci-bridge",
                "pci-bridge",
            ):
                set_cmdline_format_by_cfg(dev, self._get_cmdline_format_cfg(), "pcic")
        return devices

    def _create_attach_devices(self, spec):
        """
        Create devices for hot-plugging into a running VM instance.

        This method creates device objects from a specification for devices
        that will be hot-plugged into an already running VM instance.

        :param spec: Device specification dictionary containing device configurations
        :type spec: dict
        :return: List of device objects ready for hot-plugging
        :rtype: list
        :raises ValueError: If instance devices container is not available
        """

        def _get_tapfds(fds, dev):
            return [fd for fd in fds if os.readlink(os.path.join(qemu_fds, fd)) == dev]

        devices = []
        params = copy.deepcopy(spec)
        if self.instance_info.devices is None:
            raise ValueError

        disks = params.get("disks", [])
        if disks:
            for disk in disks:
                parent_bus = self._get_pci_parent_bus(disk.get("bus"))
                devs = qemu_devices.disk.create_disk_devices(
                    self.instance_info.devices, disk, parent_bus, self._format_cfg
                )
                self.instance_info.spec_devs.append({"spec": disk, "devices": devs})
                devices.extend(devs)

        mem = params.get("memory", [])
        if mem:
            devs = qemu_devices.memory.create_memory_devices(mem, self._format_cfg)
            self.instance_info.spec_devs.append(
                {"spec": mem.get("devices")[0], "devices": devs}
            )
            devices.extend(devs)

        nets = params.get("nets", [])
        for net in nets:
            parent_bus = self._get_pci_parent_bus(net.get("device").get("bus"))
            netdev_id = net.get("backend").get("id")
            sock_name = "-".join((self._params["name"], netdev_id, "passt.sock"))
            devs = qemu_devices.net.create_net_devices(
                self.instance_info.devices,
                net,
                parent_bus,
                self._format_cfg,
                sock_name,
                self._pass_fds,
            )
            for dev in devs:
                if isinstance(dev, qdevices.QNetdev):
                    qemu_fds = "/proc/%s/fd" % self.get_pid()
                    tun_tap_dev = "/dev/net/tun"
                    openfd_list = os.listdir(qemu_fds)
                    open_tapfd_list = _get_tapfds(openfd_list, tun_tap_dev)

                    for i in range(int(dev.get_param("queues", "1"))):
                        fd = int(dev.get_param("fd").split(":")[i])
                        fd_id = utils_misc.generate_random_id()
                        LOG.info("Assigning tap %s to qemu by fd" % fd_id, LOG.info)
                        self.monitor.cmd("getfd", {"fdname": fd_id}, fd=fd)
                        # getfd will reserve fds to qemu process, and we can close
                        # original fds after that, to avoid fd leak.
                        try:
                            os.close(fd)
                        except OSError:
                            pass
                    n_openfd_list = os.listdir(qemu_fds)
                    n_open_tapfd_list = _get_tapfds(n_openfd_list, tun_tap_dev)
                    new_tapfds = list(set(n_open_tapfd_list) - set(open_tapfd_list))
                    dev.set_param("fd", new_tapfds[0])

            self.instance_info.spec_devs.append({"spec": net, "devices": devs})
            devices.extend(devs[::-1])  # reverse the net devs for attaching

        return devices

    def _get_detach_devices(self, spec):
        """
        Get devices to be detached from the VM instance by specification.

        This method identifies and retrieves device objects that should be
        detached based on the provided specification. It searches through
        the instance's device mappings to find matching devices.

        :param spec: Device specification dictionary containing device
                     configurations to identify devices for detachment
        :type spec: dict
        :return: List of device objects to be detached
        :rtype: list
        :raises ValueError: If instance devices container is not available
        """
        devices = []
        params = copy.deepcopy(spec)
        if self.instance_info.devices is None:
            raise ValueError

        disks = params.get("disks")
        if disks:
            for disk in disks:
                for map_info in self.instance_info.spec_devs[:]:
                    if disk == map_info.get("spec"):
                        devices.append(map_info.get("devices")[-1])
                        self.instance_info.spec_devs.remove(map_info)
                        return devices

        mem = params.get("memory")
        if mem:
            for dev in mem.get("devices", []):
                for map_info in self.instance_info.spec_devs[:]:
                    if dev == map_info.get("spec"):
                        devices.extend(map_info.get("devices")[::-1])
                        self.instance_info.spec_devs.remove(map_info)
                        return devices

    def _hotplug_device(self, device, monitor=None, bus=None):
        """
        Hot-plug a device into the running VM instance.

        This method handles the low-level device hot-plugging operation,
        including bus assignment, device insertion, and verification.

        :param device: The device to hot-plug
        :type device: qdevices.QDevice or similar
        :param monitor: Monitor connection for device operations
        :type monitor: Monitor or None
        :param bus: Target bus for the device
        :type bus: Bus or None
        :return: Tuple of (output_message, success_status)
        :rtype: tuple(str, bool)
        :raises DeviceHotplugError: If the device cannot be hot-plugged
        """
        self.instance_info.devices.set_dirty()

        if isinstance(device, qdevices.QDevice):
            if bus is None:
                if self.instance_info.devices.is_pci_device(device["driver"]):
                    bus = self.instance_info.devices.get_buses({"aobject": "pci.0"})[0]
                if not isinstance(device.parent_bus, (list, tuple)):
                    device.parent_bus = [device.parent_bus]
                for parent_bus in device.parent_bus:
                    for _bus in self.instance_info.devices.get_buses(parent_bus):
                        if _bus.bus_item == "bus":
                            bus = _bus
                            break
            if bus is not None:
                bus.prepare_hotplug(device)

        try:
            # Insert the device first to assign slot
            qdev_out = self.instance_info.devices.insert(device)
            if not isinstance(qdev_out, list) or len(qdev_out) != 1:
                raise NotImplementedError(
                    "This device %s require to hotplug "
                    "multiple devices, which is not "
                    "supported." % device
                )
        except DeviceError as exc:
            raise DeviceHotplugError(device, "According to qemu_device: %s" % exc, self)
        else:
            out = device.hotplug(monitor, self.__qemu_ver)
            ver_out = device.verify_hotplug(out, monitor)
            if ver_out is False:
                self.instance_info.devices.remove(device)
            self.instance_info.devices.set_clean()

        return out, ver_out

    def _unplug_device(self, device, monitor=None, timeout=30):
        """
        Hot-unplug a device from the running VM instance.

        This method handles the low-level device hot-unplugging operation,
        including device removal, cleanup of associated resources like
        block devices, and verification of successful removal.

        :param device: The device identifier to unplug
        :type device: str or device object
        :param monitor: Monitor connection for device operations
        :type monitor: Monitor or None
        :param timeout: Timeout in seconds for the unplug operation
        :type timeout: int
        :return: Tuple of (output_message, success_status)
        :rtype: tuple(str, bool)
        :raises DeviceUnplugError: If the device cannot be unplugged
        """
        device = self.instance_info.devices[device]
        self.instance_info.devices.set_dirty()
        # Remove all devices, which are removed together with this dev
        out = device.unplug(monitor)
        # The unplug action sometimes delays for a while per host performance,
        # it will be accepted if the unplug been accomplished within 30s
        from virttest import utils_misc

        if not utils_misc.wait_for(
            lambda: device.verify_unplug(out, monitor) is True,
            first=1,
            step=5,
            timeout=timeout,
        ):
            self.instance_info.devices.set_clean()
            return out, device.verify_unplug(out, monitor)
        ver_out = device.verify_unplug(out, monitor)

        try:
            device.unplug_hook()
            drive = device.get_param("drive")
            if drive:
                if Flags.BLOCKDEV in self.instance_info.devices.caps:
                    # top node
                    node = self.instance_info.devices[drive]
                    nodes = [node]

                    # Build the full nodes list
                    for node in nodes:
                        child_nodes = node.get_child_nodes()
                        nodes.extend(child_nodes)

                    for node in nodes:
                        parent_node = node.get_parent_node()
                        child_nodes = node.get_child_nodes()
                        if not node.verify_unplug(node.unplug(monitor), monitor):
                            raise DeviceUnplugError(
                                node, "Failed to unplug blockdev node.", self
                            )
                        self.instance_info.devices.remove(
                            node, True if len(child_nodes) > 0 else False
                        )
                        if parent_node:
                            parent_node.del_child_node(node)
                else:
                    self.instance_info.devices.remove(drive)
            if ver_out is True:
                self.instance_info.devices.set_clean()
            elif out is False:
                raise DeviceUnplugError(
                    device,
                    "Device wasn't unplugged in "
                    "qemu, but it was unplugged in device "
                    "representation.",
                    self,
                )
        except (DeviceError, KeyError) as exc:
            device.unplug_unhook()
            raise DeviceUnplugError(device, exc, self)

        return out, ver_out

    def attach_device(self, device_spec, monitor_id=None):
        """
        Attach devices to the VM instance.

        This method creates devices from the specification and hot-plugs them
        into the running VM instance using the specified monitor connection.

        :param device_spec: Device specification for creating devices
        :type device_spec: dict
        :param monitor_id: Optional monitor connection ID to use
        :type monitor_id: str or None
        :return: Tuple of (output_message, success_status)
        :rtype: tuple(str, bool)
        """
        devs = self._create_attach_devices(device_spec)
        if monitor_id:
            monitor = connect_mgr.get_connection(monitor_id)
        else:
            monitor = self.monitor
        for dev in devs:
            out, ver_out = self._hotplug_device(dev, monitor)
            if ver_out is False:
                return out, ver_out
        else:
            return "", True

    def detach_device(self, device_spec, monitor_id=None, timeout=30):
        """
        Detach devices from the VM instance.

        This method identifies devices to detach based on the specification
        and hot-unplugs them from the running VM instance using the specified
        monitor connection.

        :param device_spec: Device specification for identifying devices to detach
        :type device_spec: dict
        :param monitor_id: Optional monitor connection ID to use
        :type monitor_id: str or None
        :param timeout: Timeout in seconds for the unplug operation
        :type timeout: int
        :return: Tuple of (output_message, success_status)
        :rtype: tuple(str, bool)
        """
        devs = self._get_detach_devices(device_spec)
        if monitor_id:
            monitor = connect_mgr.get_connection(monitor_id)
        else:
            monitor = self.monitor
        for dev in devs:
            out, ver_out = self._unplug_device(dev, monitor, timeout)
            if ver_out is False:
                return out, ver_out
        else:
            return "", True

    def _incoming_cmd(self, migrate_inc_uri):
        """
        Generate the QEMU command line argument for incoming migration.

        :param migrate_inc_uri: The migration URI for incoming migration
        :type migrate_inc_uri: str
        :return: The formatted -incoming command line argument
        :rtype: str
        """
        if self.instance_info.devices.has_option("incoming defer"):
            migrate_inc_uri = "defer"
        incoming_cmd = f" -incoming {migrate_inc_uri}"

        return incoming_cmd

    def make_create_cmdline(self):
        """
        Create the complete QEMU command line for instance creation.

        This method builds the full QEMU command line by creating devices
        based on the instance specification and optionally adding migration
        incoming parameters if configured.

        :return: The complete QEMU command line string
        :rtype: str
        """
        devices = self._create_devices(self.instance_info.spec)
        self.instance_info.devices = devices

        migrate_incoming = self.instance_info.migrate_incoming
        migrate_inc_uri = migrate_incoming.get("uri") if migrate_incoming else None

        if migrate_inc_uri:
            self._migrate_inc_uri = migrate_inc_uri
        cmdline = devices.cmdline()

        if migrate_inc_uri:
            cmdline += self._incoming_cmd(migrate_inc_uri)

        return cmdline

    def _verify_status(self, status):
        """
        Check VM instance status

        :param status: Optional VM status, 'running' or 'paused'
        :raise VMStatusError: If the VM status is not same as parameter
        """
        o = dict(self.monitor.cmd(cmd="query-status", debug=False))
        if status == "paused":
            return o["running"] is False
        if status == "running":
            return o["running"] is True
        if o["status"] == status:
            return True
        return False

    def _wait_for_status(self, status, timeout, first=0.0, step=1.0, text=None):
        """
        Wait until the VM status changes to specified status

        :param timeout: Timeout in seconds
        :param first: Time to sleep before first attempt
        :param steps: Time to sleep between attempts in seconds
        :param text: Text to print while waiting, for debug purposes

        :return: True in case the status has changed before timeout, otherwise
                 return None.
        """
        return utils_misc.wait_for(
            lambda: self.monitor.verify_status(status), timeout, first, step, text
        )

    def pause(self):
        """
        Pause the currently running QEMU virtual machine instance.

        Sends a 'stop' command to the QEMU monitor to suspend VM execution
        while preserving memory state. The instance can be resumed later.

        :raises VMStatusError: If the VM fails to enter paused state
        """
        self.monitor.cmd("stop")
        self._verify_status("paused")

    def is_paused(self):
        """
        Check if the QEMU virtual machine instance is currently paused.

        :return: True if the VM status is 'paused', False otherwise
        :rtype: bool
        """
        return self._verify_status("paused")

    def resume(self, timeout=60):
        """
        Resume a paused QEMU virtual machine instance.

        Sends a 'cont' command to the QEMU monitor to restore VM execution
        from the paused state. If timeout is specified, waits for the VM
        to enter running state within the timeout period.

        :param timeout: Maximum time to wait for VM to enter running state.
                       If 0, does not wait and only verifies status once.
        :type timeout: int
        :raises VMStatusError: If the VM fails to enter running state within timeout
        """
        self.monitor.cmd("cont")
        if timeout:
            if not self._wait_for_status("running", timeout, step=0.1):
                raise virt_vm.VMStatusError(
                    "Failed to enter running status, "
                    "the actual status is %s" % self.monitor.get_status()
                )
        else:
            self._verify_status("running")

    def is_running(self):
        """
        Check if the QEMU virtual machine instance is currently running.

        :return: True if the VM status is 'running', False otherwise
        :rtype: bool
        """
        return self._verify_status("running")
