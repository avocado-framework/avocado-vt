import logging
import os
import time
import shutil
import re
import json

import aexpect

import signal

from avocado.utils import process
from six.moves import xrange

from functools import partial, reduce
from operator import mul

from virttest import arch
from virttest import cpu as cpu_utils
from virttest import data_dir, utils_logfile, utils_misc, utils_qemu
from virttest.qemu_capabilities import Flags
from virttest.qemu_devices import qcontainer, qdevices
from virttest.qemu_devices.utils import DeviceError
from virttest.utils_params import Params
from virttest.utils_version import VersionInterval
from virttest import virt_vm
from virttest.qemu_devices.utils import set_cmdline_format_by_cfg

from vt_agent.core.data_dir import LOG_DIR
from vt_agent.core import data_dir as core_data_dir

from managers import console_mgr

try:
    from virttest.vt_utils import image
except ImportError:
    pass

# from core import data_dir
from . import InstanceDriver

LOG = logging.getLogger("avocado.service." + __name__)


PARAMETERS_MAPPING = {
    "COMPRESS_LEVEL": {
        "options": ("compress-level", ),
        "source_party": True,
        "destination_party": True
    },

    "COMPRESS_THREADS": {
        "options": ("compress-threads", ),
        "source_party": True,
        "destination_party": True,
    },

    "DECOMPRESS_THREADS": {
        "options": ("decompress-threads", ),
        "source_party": True,
        "destination_party": True,
    },

    "THROTTLE_INITIAL": {
        "options": ("cpu-throttle-initial", ),
        "source_party": True,
        "destination_party": False,
    },

    "THROTTLE_INCREMENT": {
        "options": ("cpu-throttle-increment", ),
        "source_party": True,
        "destination_party": False,
    },

    # "TLS_CREDS": {
    #     "options": ("tls-creds", ),
    #     "source_party": True,
    #     "destination_party": True,
    # },

    "TLS_HOSTNAME": {
        "options": ("tls-hostname", ),
        "source_party": True,
        "destination_party": False,
    },

    # "MAX_BANDWIDTH": {
    #     "options": ("max-bandwidth", ),
    #     "source_party": True,
    #     "destination_party": True,
    # },

    # "DOWNTIME_LIMIT": {
    #     "options": ("downtime-limit", ),
    #     "source_party": True,
    #     "destination_party": True,
    # },

    # "BLOCK_INCREMENTAL": {
    #     "options": ("block-incremental", ),
    #     "source_party": True,
    #     "destination_party": True,
    # },

    "XBZRLE_CACHE_SIZE": {
        "options": ("xbzrle-cache-size", ),
        "source_party": True,
        "destination_party": True,
    },

    "MAX_POSTCOPY_BANDWIDTH": {
        "options": ("max-postcopy-bandwidth", ),
        "source_party": True,
        "destination_party": True,
    },

    "MULTIFD_CHANNELS": {
        "options": ("multifd-channels", ),
        "source_party": True,
        "destination_party": True,
    },

    # "MULTIFD_COMPRESSION": {
    #     "options": ("multifd-compression", ),
    #     "source_party": True,
    #     "destination_party": True,
    # },

    "MULTIFD_ZLIB_LEVEL": {
        "options": ("multifd-zlib-level", ),
        "source_party": True,
        "destination_party": True,
    },

    "MULTIFD_ZSTD_LEVEL": {
        "options": ("multifd-zstd-level", ),
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


class QemuInstanceDriver(InstanceDriver):
    def __init__(self, instance_id):
        super(QemuInstanceDriver, self).__init__(instance_id, "qemu")
        self._process = None
        self._migrate_inc_uri = None

    def _qemu_proc_term_handler(self, monitor_exit_status, exit_status):
        """Monitors qemu process unexpected exit.

        Callback function to detect QEMU process non-zero exit status and
        push VMExitStatusError to background error bus.
        """
        devices = self._devices
        for snapshot in devices.temporary_image_snapshots:
            try:
                os.unlink(snapshot)
            except OSError:
                pass
        devices.temporary_image_snapshots.clear()

    def _start_daemons(self):
        """Start the daemons of qemu device."""
        if self._devices:
            for dev in self._devices:
                if isinstance(dev, qdevices.QDaemonDev):
                    dev.start_daemon()

    def start(self, command):
        self._start_daemons()
        LOG.info(
            "<Instance: %s> Running qemu command (reformatted):\n%s", self._instance_id,
            "<Instance: %s>    -" % self._instance_id + command.replace(
                " -", " \\\n<Instance: %s>    -" % self._instance_id),
        )
        self._process = aexpect.run_tail(
            command=command,
            termination_func=partial(self._qemu_proc_term_handler, False),
            output_func=LOG.info,
            output_prefix="<Instance: %s> [qemu output] " % self._instance_id,
            auto_close=False,
            pass_fds=(),
        )

        LOG.info("<Instance: %s> Created qemu process with parent PID %d",
                 self._instance_id, self._process.get_pid())

        # Make sure qemu is not defunct
        if self._process.is_defunct():
            LOG.error("Bad things happened, qemu process is defunct")
            err = "Qemu is defunct.\nQemu output:\n%s" % self._process.get_output()
            raise virt_vm.VMStartError(self._instance_id, err)

        # Make sure the process was started successfully
        if not self._process.is_alive():
            status = self._process.get_status()
            output = self._process.get_output().strip()
            # migration_protocol = self._migrate_inc_uri.get("protocol")
            migration_in_course = self._migrate_inc_uri is not None
            unknown_protocol = "unknown migration protocol" in output
            if migration_in_course and unknown_protocol:
                e = VMMigrateProtoUnsupportedError(self._migrate_inc_uri, output)
            else:
                e = virt_vm.VMCreateError(command, status, output)
            raise e

        # Get the output so far, to see if we have any problems with
        # KVM modules or with hugepage setup.
        output = self._process.get_output()

        if re.search("Could not initialize KVM", output, re.IGNORECASE):
            e = virt_vm.VMKVMInitError(command, self._process.get_output())
            raise e

        if "alloc_mem_area" in output:
            e = virt_vm.VMHugePageError(command, self._process.get_output())
            raise e

        LOG.debug("<Instance: %s> Instance appears to be alive with PID %s",
                  self._instance_id, self.get_pid())

    def _stop_daemons(self):
        """Stop the daemons of qemu device."""
        if self._devices:
            for dev in self._devices:
                if isinstance(dev, qdevices.QDaemonDev):
                    try:
                        dev.stop_daemon()
                    except DeviceError as err:
                        LOG.error("Failed to stop daemon: %s", err)

    def _is_dead(self):
        """
        Return True if the qemu process is dead.
        """
        return not self._process or not self._process.is_alive()

    def wait_until_paused(self, timeout):
        """
        Wait until the VM is paused.

        :param timeout: Timeout in seconds.

        :return: True in case the VM is paused before timeout, otherwise
                 return None.
        """
        return self.wait_for_status("paused", timeout)

    def _wait_until_dead(self, timeout, first=0.0, step=1.0):
        """
        Wait until VM is dead.

        :return: True if VM is dead before timeout, otherwise returns None.

        :param timeout: Timeout in seconds
        :param first: Time to sleep before first attempt
        :param steps: Time to sleep between attempts in seconds
        """
        return utils_misc.wait_for(self._is_dead, timeout, first, step)

    def wait_for_shutdown(self, timeout=60):
        """
        Wait until guest shuts down.

        Helps until the VM is shut down by the guest.

        :return: True in case the VM was shut down, None otherwise.

        Note that the VM is not necessarily dead when this function returns
        True. If QEMU is running in -no-shutdown mode, the QEMU process
        may be still alive.
        """
        self.no_shutdown = False # FIXME: hard code to set this here
        if self.no_shutdown:
            return self.wait_until_paused(timeout)
        else:
            return self._wait_until_dead(timeout, 1, 1)

    def serial_login(self, username=None, password=None, prompt=None, timeout=None):
        consoles = console_mgr.get_consoles_by_instance(self._instance_id)
        if not consoles:
            # LOG.error("No consoles found for instance %s", self._instance_id)
            # return None
            raise ValueError(f"No consoles found for instance {self._instance_id}")
        serial = consoles[0]
        aexpect.remote.handle_prompts(serial, username, password, prompt, timeout)
        return serial

    def graceful_shutdown(self, shutdown_cmd=None, username=None,
                          password=None, prompt=None, timeout=60):
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
                if self.wait_for_shutdown(timeout):
                    return True
            finally:
                session.close()

        if shutdown_cmd:
            # Try to destroy with shell command
            LOG.debug("Shutting down instance %s (shell)", self._instance_id)
            try:
                # FIXME: Login via serial mandatory
                session = self.serial_login(username, password, prompt, timeout)
            except (IndexError) as e:
                try:
                    session = self.serial_login(username, password, prompt, timeout)
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

    def stop(self, graceful=True, timeout=60, shutdown_cmd=None,
             username=None, password=None, prompt=None):
        try:
            # Is it already dead?
            if self._is_dead():
                return

            LOG.debug("Destroying the instance %s (PID %s)",
                      self._instance_id, self.get_pid())
            if graceful:
                self.graceful_shutdown(shutdown_cmd, username,
                                       password, prompt, timeout)
                if self._is_dead():
                    LOG.debug("Instance %s down (shell)", self._instance_id)
                    return
                else:
                    LOG.debug("Instance %s failed to go down (shell)", self._instance_id)

            if self.monitor:
                # Try to finish process with a monitor command
                LOG.debug("Ending the instance %s process (monitor)",
                          self._instance_id)
                try:
                    self.monitor.quit()
                except Exception as e:
                    LOG.warn(e)
                    if self._is_dead():
                        LOG.warn(
                            "Instance %s down during try to kill it by monitor",
                            self._instance_id
                        )
                        return
                else:
                    # Wait for the VM to be really dead
                    if self._wait_until_dead(5, 0.5, 0.5):
                        LOG.debug("Instance %s down (monitor)",
                                  self._instance_id)
                        return
                    else:
                        LOG.debug("Instance %s failed to go down (monitor)",
                                  self._instance_id)

            # If the VM isn't dead yet...
            pid = self._process.get_pid()
            LOG.debug("Ending Instance %s process (killing PID %s)",
                      self._instance_id, pid)
            try:
                utils_misc.kill_process_tree(pid, 9, timeout=60)
                LOG.debug("Instance %s down (process killed)",
                          self._instance_id)
            except RuntimeError:
                # If all else fails, we've got a zombie...
                LOG.error(
                    "Instance %s (PID %s) is a zombie!",
                    self._instance_id, self._process.get_pid()
                )
        finally:
            self._stop_daemons()

    def cleanup_serial_console(self):
        """
        Close serial console and associated log file
        """
        pass

    def cleanup(self, free_mac_addresses=True):
        self.monitors = []
        # if self.pci_assignable:
        #     self.pci_assignable.release_devs()
        #     self.pci_assignable = None
        if self._process:
            self._process.close()
        self.cleanup_serial_console()
        # if self.logsessions:
        #     for key in self.logsessions:
        #         self.logsessions[key].close()

        # Generate the tmp file which should be deleted.
        # file_list = [self.get_testlog_filename()]
        # file_list += qemu_monitor.get_monitor_filenames(self)
        # file_list += self.get_serial_console_filenames()
        # file_list += list(self.logs.values())
        #
        # for f in file_list:
        #     try:
        #         if f:
        #             os.unlink(f)
        #     except OSError:
        #         pass

        # if hasattr(self, "migration_file"):
        #     try:
        #         os.unlink(self.migration_file)
        #     except OSError:
        #         pass

        # if free_mac_addresses:
        #     for nic_index in xrange(0, len(self.virtnet)):
        #         self.free_mac_address(nic_index)
        #
        # port_mapping = {}
        # for nic in self.virtnet:
        #     if nic.nettype == "macvtap":
        #         tap = utils_net.Macvtap(nic.ifname)
        #         tap.delete()
        #     elif nic.ifname:
        #         port_mapping[nic.ifname] = nic
        #
        # if port_mapping:
        #     queues_num = sum([int(_.queues) for _ in port_mapping.values()])
        #     deletion_time = max(5, math.ceil(queues_num / 8))
        #     utils_misc.wait_for(
        #         lambda: set(port_mapping.keys()).isdisjoint(utils_net.get_net_if()),
        #         deletion_time,
        #     )
        #     for inactive_port in set(port_mapping.keys()).difference(
        #         utils_net.get_net_if()
        #     ):
        #         nic = port_mapping.pop(inactive_port)
        #         self._del_port_from_bridge(nic)
        #     for active_port in port_mapping.keys():
        #         LOG.warning("Deleting %s failed during tap cleanup" % active_port)

    def _create_monitor_consoles(self):
        # Establish monitor connections
        for monitor in self._params.get("monitors"):
            monitor_id = monitor.get("id")

        # for monitor in self._parmas.get("monitors"):
        #     m_params = params.object_params(m_name)
        #     if m_params.get("debugonly", "no") == "yes":
        #         continue
        #     try:
        #         monitor = qemu_monitor.wait_for_create_monitor(
        #             self, m_name, m_params, timeout
        #         )
        #         self._monitors.append(monitor)
        #     except qemu_monitor.MonitorConnectError as detail:
        #         LOG.error(detail)
        #         raise detail

    def _create_serial_console(self):
        pass

    def create_console_connections(self):
        self._create_monitor_consoles()
        self._create_serial_console()

        # self.create_serial_console()
        #
        # for key, value in list(self.logs.items()):
        #     outfile = os.path.join(
        #         utils_logfile.get_log_file_dir(), "%s-%s.log" % (key, name)
        #     )
        #     self.logsessions[key] = aexpect.Tail(
        #         "nc -U %s" % value,
        #         auto_close=False,
        #         output_func=utils_logfile.log_line,
        #         output_params=(outfile,),
        #     )
        #     self.logsessions[key].close_hooks += [
        #         utils_logfile.close_own_log_file(outfile)
        #     ]
        #
        # # Wait for IO channels setting up completely,
        # # such as serial console.
        # time.sleep(1)
        #
        # if is_preconfig:
        #     return
        #
        # if params.get("paused_after_start_vm") != "yes":
        #     # start guest
        #     if self.monitor.verify_status("paused"):
        #         if not migration_mode:
        #             self.resume()
        #
        # # Update mac and IP info for assigned device
        # # NeedFix: Can we find another way to get guest ip?
        # if params.get("mac_changeable") == "yes":
        #     utils_net.update_mac_ip_address(self)

    def get_proc_info(self, name):
        if name == "pid":
            return self._process.get_pid()
        elif name == "status":
            return self._process.get_status()
        elif name == "output":
            return self._process.get_output()
        elif name == "alive":
            return self._process.is_alive()
        elif name == "defunct":
            return self._process.is_defunct()
        else:
            raise ValueError(f"Unknown information {name}")

    def kill_proc(self, sig=signal.SIGKILL):
        self._process.kill(sig)

    def get_pid(self):
        try:
            cmd = "ps --ppid=%d -o pid=" % self._process.get_pid()
            children = process.run(
                cmd, verbose=False, ignore_status=True
            ).stdout_text.split()
            return int(children[0])
        except (TypeError, IndexError, ValueError):
            return None

    def _get_pci_parent_bus(self, bus):
        if bus:
            parent_bus = {"aobject": bus}
        else:
            parent_bus = None
        return parent_bus

    def _create_sandbox_device(self, sandbox):
        sandbox_option = ""
        action = sandbox.get("action")
        if action == "on":
            sandbox_option = " -sandbox on"
        elif action == "off":
            sandbox_option = " -sandbox off"

        props = sandbox.get("props")
        if props:
            for opt, val in props.items():
                if val is not None:
                    sandbox_option += f",{opt}={val}"

        return qdevices.QStringDevice("qemu_sandbox", cmdline=sandbox_option)

    def _create_firmware_devices(self, firmware):
        # FIXME:
        devs = []
        # cmdline = "-blockdev '{\"node-name\": \"file_ovmf_code\", " \
        #           "\"driver\": \"file\", \"filename\": \"/usr/share/OVMF/OVMF_CODE.secboot.fd\", " \
        #           "\"auto-read-only\": true, \"discard\": \"unmap\"}'"
        # dev = qdevices.QStringDevice("file_ovmf_code", cmdline=cmdline)
        # devs.append(dev)
        #
        # cmdline = "-blockdev '{\"node-name\": \"drive_ovmf_code\", " \
        #           "\"driver\": \"raw\", \"read-only\": true, \"file\": \"file_ovmf_code\"}'"
        # dev = qdevices.QStringDevice("drive_ovmf_code", cmdline=cmdline)
        # devs.append(dev)
        #
        # cmdline = "-blockdev '{\"node-name\": \"file_ovmf_vars\", " \
        #           "\"driver\": \"file\", \"filename\": \"/home/yhong/kar/workspace/root/avocado/data/" \
        #           "avocado-vt/avocado-vt-vm1_rhel950-64-virtio-scsi-ovmf_qcow2_filesystem_VARS.raw\", " \
        #           "\"auto-read-only\": true, \"discard\": \"unmap\"}'"
        # dev = qdevices.QStringDevice("file_ovmf_vars", cmdline=cmdline)
        # devs.append(dev)
        #
        # cmdline = "-blockdev '{\"node-name\": \"drive_ovmf_vars\", " \
        #           "\"driver\": \"raw\", \"read-only\": false, \"file\": \"file_ovmf_vars\"}'"
        # dev = qdevices.QStringDevice("file_ovmf_vars", cmdline=cmdline)
        # devs.append(dev)
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
            pflash_vars_path = os.path.join(core_data_dir.get_data_dir(), pflash_vars_path)
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

    def _create_machine_devices(self, machine):
        # def create_pcic(name, params, parent_bus=None):
        #     """
        #     Creates pci controller/switch/... based on params
        #
        #     :param name: Autotest name
        #     :param params: PCI controller params
        #     :note: x3130 creates x3130-upstream bus + xio3130-downstream port for
        #            each inserted device.
        #     :warning: x3130-upstream device creates only x3130-upstream device
        #               and you are responsible for creating the downstream ports.
        #     """
        #     driver = params.get("type", "pcie-root-port")
        #     pcic_params = {"id": name}
        #     if driver in ("pcie-root-port", "ioh3420", "x3130-upstream", "x3130"):
        #         bus_type = "PCIE"
        #     else:
        #         bus_type = "PCI"
        #     if not parent_bus:
        #         parent_bus = [{"aobject": params.get("pci_bus", "pci.0")}]
        #     elif not isinstance(parent_bus, (list, tuple)):
        #         parent_bus = [parent_bus]
        #     if driver == "x3130":
        #         bus = qdevices.QPCISwitchBus(name, bus_type, "xio3130-downstream", name)
        #         driver = "x3130-upstream"
        #     else:
        #         if driver == "pci-bridge":  # addr 0x01-0x1f, chasis_nr
        #             parent_bus.append({"busid": "_PCI_CHASSIS_NR"})
        #             bus_length = 32
        #             bus_first_port = 1
        #         elif driver == "i82801b11-bridge":  # addr 0x1-0x13
        #             bus_length = 20
        #             bus_first_port = 1
        #         elif driver in ("pcie-root-port", "ioh3420"):
        #             bus_length = 1
        #             bus_first_port = 0
        #             parent_bus.append({"busid": "_PCI_CHASSIS"})
        #         elif driver == "pcie-pci-bridge":
        #             params["reserved_slots"] = "0x0"
        #             # Unsupported PCI slot 0 for standard hotplug controller.
        #             # Valid slots are between 1 and 31
        #             bus_length = 32
        #             bus_first_port = 1
        #         else:  # addr = 0x0-0x1f
        #             bus_length = 32
        #             bus_first_port = 0
        #         bus = qdevices.QPCIBus(name, bus_type, name, bus_length, bus_first_port)
        #     for addr in params.get("reserved_slots", "").split():
        #         bus.reserve(addr)
        #     return qdevices.QDevice(
        #         driver, pcic_params, aobject=name, parent_bus=parent_bus, child_bus=bus
        #     )

        def create_machine_q35(machine_props):
            """
            Q35 + ICH9
            """
            devices = []
            pcie_root_port_params = None
            cpu_model = None
            if self._params["cpu"]["info"]["model"]:
                cpu_model = self._params["cpu"]["info"]["model"]
            controller = self._params["controllers"][0]
            root_port_type = controller.get("type")
            controller_props = controller.get("props")
            if controller_props:
                pcie_root_port_params = controller_props.get("root_port_props")
            bus = (
                qdevices.QPCIEBus(
                    "pcie.0", "PCIE", root_port_type, "pci.0", pcie_root_port_params
                ),
                qdevices.QStrictCustomBus(
                    None, [["chassis"], [256]], "_PCI_CHASSIS", first_port=[1]
                ),
                qdevices.QStrictCustomBus(
                    None, [["chassis_nr"], [256]], "_PCI_CHASSIS_NR", first_port=[1]
                ),
                qdevices.QCPUBus(cpu_model, [[""], [0]], "vcpu"),
            )
            # pflash_devices = pflash_handler("ovmf", machine_params)
            # devices.extend(pflash_devices)
            # FIXME: hard code workaround to add pflash related devices infiormation
            machine_props["pflash0"] = "drive_ovmf_code"
            machine_props["pflash1"] = "drive_ovmf_vars"
            machine_props["memory-backend"] = "mem-machine_mem"
            devices.append(
                qdevices.QMachine(params=machine_props, child_bus=bus, aobject="pci.0")
            )
            devices.append(
                qdevices.QStringDevice(
                    "mch", {"addr": 0, "driver": "mch"}, parent_bus={"aobject": "pci.0"}
                )
            )
            devices.append(
                qdevices.QStringDevice(
                    "ICH9-LPC",
                    {"addr": "1f.0", "driver": "ICH9-LPC"},
                    parent_bus={"aobject": "pci.0"},
                )
            )
            devices.append(
                qdevices.QStringDevice(
                    "ICH9 SMB",
                    {"addr": "1f.3", "driver": "ICH9 SMB"},
                    parent_bus={"aobject": "pci.0"},
                )
            )
            devices.append(
                qdevices.QStringDevice(
                    "ICH9-ahci",
                    {"addr": "1f.2", "driver": "ich9-ahci"},
                    parent_bus={"aobject": "pci.0"},
                    child_bus=qdevices.QAHCIBus("ide"),
                )
            )
            if self._devices.has_option("device") and self._devices.has_option("global"):
                devices.append(
                    qdevices.QStringDevice(
                        "fdc", child_bus=qdevices.QFloppyBus("floppy")
                    )
                )
            else:
                devices.append(
                    qdevices.QStringDevice(
                        "fdc", child_bus=qdevices.QOldFloppyBus("floppy")
                    )
                )

            return devices

        def create_machine_i440fx(machine_props):
            """
            i440FX + PIIX
            """
            devices = []
            pci_bus = "pci.0"
            cpu_model = None
            if self._params["cpu"]["info"]["model"]:
                cpu_model = self._params["cpu"]["info"]["model"]

            bus = (
                qdevices.QPCIBus(pci_bus, "PCI", "pci.0"),
                qdevices.QStrictCustomBus(
                    None, [["chassis"], [256]], "_PCI_CHASSIS", first_port=[1]
                ),
                qdevices.QStrictCustomBus(
                    None, [["chassis_nr"], [256]], "_PCI_CHASSIS_NR", first_port=[1]
                ),
                qdevices.QCPUBus(cpu_model, [[""], [0]], "vcpu"),
            )
            # TODO: support pflash devices
            # pflash_devices = pflash_handler("ovmf", machine_params)
            # devices.extend(pflash_devices)
            devices.append(
                qdevices.QMachine(params=machine_props, child_bus=bus, aobject="pci.0")
            )
            devices.append(
                qdevices.QStringDevice(
                    "i440FX",
                    {"addr": 0, "driver": "i440FX"},
                    parent_bus={"aobject": "pci.0"},
                )
            )
            devices.append(
                qdevices.QStringDevice(
                    "PIIX4_PM",
                    {"addr": "01.3", "driver": "PIIX4_PM"},
                    parent_bus={"aobject": "pci.0"},
                )
            )
            devices.append(
                qdevices.QStringDevice(
                    "PIIX3",
                    {"addr": 1, "driver": "PIIX3"},
                    parent_bus={"aobject": "pci.0"},
                )
            )
            devices.append(
                qdevices.QStringDevice(
                    "piix3-ide",
                    {"addr": "01.1", "driver": "piix3-ide"},
                    parent_bus={"aobject": "pci.0"},
                    child_bus=qdevices.QIDEBus("ide"),
                )
            )
            if self._devices.has_option("device") and self._devices.has_option("global"):
                devices.append(
                    qdevices.QStringDevice(
                        "fdc", child_bus=qdevices.QFloppyBus("floppy")
                    )
                )
            else:
                devices.append(
                    qdevices.QStringDevice(
                        "fdc", child_bus=qdevices.QOldFloppyBus("floppy")
                    )
                )
            return devices

        def create_machine_pseries(machine_props):
            """
             Pseries, not full support yet.
             """
            # TODO: This one is copied from machine_i440FX, in order to
            #  distinguish it from the i440FX, its bus structure will be
            #  modified in the future.
            devices = []
            cpu_model = None
            if self._params["cpu"]["info"]["model"]:
                cpu_model = self._params["cpu"]["info"]["model"]
            pci_bus = "pci.0"
            bus = (
                qdevices.QPCIBus(pci_bus, "PCI", "pci.0"),
                qdevices.QStrictCustomBus(
                    None, [["chassis"], [256]], "_PCI_CHASSIS", first_port=[1]
                ),
                qdevices.QStrictCustomBus(
                    None, [["chassis_nr"], [256]], "_PCI_CHASSIS_NR",
                    first_port=[1]
                ),
                qdevices.QCPUBus(cpu_model, [[""], [0]], "vcpu"),
            )
            devices.append(
                qdevices.QMachine(params=machine_props, child_bus=bus,
                                  aobject="pci.0")
            )
            devices.append(
                qdevices.QStringDevice(
                    "i440FX",
                    {"addr": 0, "driver": "i440FX"},
                    parent_bus={"aobject": "pci.0"},
                )
            )
            devices.append(
                qdevices.QStringDevice(
                    "PIIX4_PM",
                    {"addr": "01.3", "driver": "PIIX4_PM"},
                    parent_bus={"aobject": "pci.0"},
                )
            )
            devices.append(
                qdevices.QStringDevice(
                    "PIIX3",
                    {"addr": 1, "driver": "PIIX3"},
                    parent_bus={"aobject": "pci.0"},
                )
            )
            devices.append(
                qdevices.QStringDevice(
                    "piix3-ide",
                    {"addr": "01.1", "driver": "piix3-ide"},
                    parent_bus={"aobject": "pci.0"},
                    child_bus=qdevices.QIDEBus("ide"),
                )
            )
            if self._devices.has_option("device") and self._devices.has_option("global"):
                devices.append(
                    qdevices.QStringDevice(
                        "fdc", child_bus=qdevices.QFloppyBus("floppy")
                    )
                )
            else:
                devices.append(
                    qdevices.QStringDevice(
                        "fdc", child_bus=qdevices.QOldFloppyBus("floppy")
                    )
                )
            return devices

        def create_machine_s390_virtio(machine_props):
            """
            s390x (s390) doesn't support PCI bus.
            """
            devices = []
            cpu_model = None
            if self._params["cpu"]["info"]["model"]:
                cpu_model = self._params["cpu"]["info"]["model"]
            # Add virtio-bus
            # TODO: Currently this uses QNoAddrCustomBus and does not
            # set the device's properties. This means that the qemu qtree
            # and autotest's representations are completely different and
            # can't be used.
            LOG.warn("Support for s390x is highly experimental!")
            bus = (
                qdevices.QNoAddrCustomBus(
                    "bus",
                    [["addr"], [64]],
                    "virtio-blk-ccw",
                    "virtio-bus",
                    "virtio-blk-ccw",
                ),
                qdevices.QNoAddrCustomBus(
                    "bus", [["addr"], [32]], "virtual-css", "virtual-css", "virtual-css"
                ),
                qdevices.QCPUBus(cpu_model, [[""], [0]], "vcpu"),
            )
            devices.append(
                qdevices.QMachine(
                    params=machine_props, child_bus=bus, aobject="virtio-blk-ccw"
                )
            )
            return devices

        def create_machine_arm64_pci(machine_props):
            """
            Experimental support for pci-based aarch64
            """
            LOG.warn("Support for aarch64 is highly experimental!")
            devices = []

            controller = self._params["controllers"][0]
            root_port_type = controller.get("type")
            controller_props = controller.get("props")
            if controller_props:
                pcie_root_port_params = controller_props.get("root_port_props")

            bus = (
                qdevices.QPCIEBus(
                    "pcie.0", "PCIE", root_port_type, "pci.0", pcie_root_port_params
                ),
                qdevices.QStrictCustomBus(
                    None, [["chassis"], [256]], "_PCI_CHASSIS", first_port=[1]
                ),
                qdevices.QStrictCustomBus(
                    None, [["chassis_nr"], [256]], "_PCI_CHASSIS_NR", first_port=[1]
                ),
            )
            # pflash_devices = pflash_handler("aavmf", machine_params)
            # devices.extend(pflash_devices)
            devices.append(
                qdevices.QMachine(params=machine_props, child_bus=bus, aobject="pci.0")
            )
            devices.append(
                qdevices.QStringDevice(
                    "gpex-root",
                    {"addr": 0, "driver": "gpex-root"},
                    parent_bus={"aobject": "pci.0"},
                )
            )

            return devices

        def create_machine_arm64_mmio(machine_props):
            """
            aarch64 (arm64) doesn't support PCI bus, only MMIO transports.
            Also it requires pflash for EFI boot.
            """
            LOG.warn("Support for aarch64 is highly experimental!")
            devices = []
            # Add virtio-bus
            # TODO: Currently this uses QNoAddrCustomBus and does not
            # set the device's properties. This means that the qemu qtree
            # and autotest's representations are completely different and
            # can't be used.
            bus = qdevices.QNoAddrCustomBus(
                "bus",
                [["addr"], [32]],
                "virtio-mmio-bus",
                "virtio-bus",
                "virtio-mmio-bus",
            )
            # pflash_devices = pflash_handler("aavmf", machine_params)
            # devices.extend(pflash_devices)
            devices.append(
                qdevices.QMachine(
                    params=machine_props, child_bus=bus, aobject="virtio-mmio-bus"
                )
            )
            return devices

        def create_machine_riscv64_mmio(machine_props):
            """
            riscv doesn't support PCI bus, only MMIO transports.
            """
            LOG.warn(
                "Support for riscv64 is highly experimental. See "
                "https://avocado-vt.readthedocs.io"
                "/en/latest/Experimental.html#riscv64 for "
                "setup information."
            )
            devices = []
            # Add virtio-bus
            # TODO: Currently this uses QNoAddrCustomBus and does not
            # set the device's properties. This means that the qemu qtree
            # and autotest's representations are completely different and
            # can't be used.
            bus = qdevices.QNoAddrCustomBus(
                "bus",
                [["addr"], [32]],
                "virtio-mmio-bus",
                "virtio-bus",
                "virtio-mmio-bus",
            )
            devices.append(
                qdevices.QMachine(
                    params=machine_props, child_bus=bus, aobject="virtio-mmio-bus"
                )
            )
            return devices

        def create_machine_other(machine_props):
            """
            isapc or unknown machine type. This type doesn't add any default
            buses or devices, only sets the cmdline.
            """
            LOG.warn(
                "Machine type isa/unknown is not supported by "
                "avocado-vt. False errors might occur"
            )
            devices = [qdevices.QMachine(params=machine_props)]
            return devices

        machine_type = machine.get("type")
        machine_props = machine.get("props")
        # machine_controllers = machine.get("controllers")
        #
        # if self._devices.has_device("pcie-root-port"):
        #     root_port_type = "pcie-root-port"
        # else:
        #     root_port_type = "ioh3420"
        #
        # if self._devices.has_device("pcie-pci-bridge"):
        #     pci_bridge_type = "pcie-pci-bridge"
        # else:
        #     pci_bridge_type = "pci-bridge"

        # FIXME: workaround for invalid_machine is None
        avocado_machine = ""
        machine_params = machine_props.copy()

        # if invalid_machine is not None:
        #     devices = invalid_machine({"type": machine_type})
        # cpu_controller = dict()
        pcie_controller = dict()
        if ":" in machine_type: # FIXME: To support the arm architecture
            avocado_machine, machine_type = machine_type.split(":", 1)
        machine_params["type"] = machine_type

        if avocado_machine == "invalid_machine":
            devices = create_machine_i440fx({"type": machine_type})
        elif machine_type == "pc" or "i440fx" in machine_type:
            devices = create_machine_i440fx(machine_params)
        elif "q35" in machine_type:
            devices = create_machine_q35(machine_params)
        elif machine_type.startswith("pseries"):
            devices = create_machine_pseries(machine_params)
        elif machine_type.startswith("s390"):
            devices = create_machine_s390_virtio(machine_params)
        # FIXME: support the arm architecture by avocado_machine
        elif avocado_machine == "arm64-pci":
            devices = create_machine_arm64_pci(machine_params)
        elif avocado_machine == "arm64-mmio":
            devices = create_machine_arm64_mmio(machine_params)
        elif avocado_machine == "riscv64-mmio":
            devices = create_machine_riscv64_mmio(machine_params)
        else:
            LOG.warn(
                "Machine type '%s' is not supported "
                "by avocado-vt, errors might occur",
                machine_type,
            )
            devices = create_machine_other(machine_params)

        # FIXME: Skip this part because can not make sure what does it do
        # reserve pci.0 addresses
        # pci_params = params.object_params("pci.0")
        # reserved = pci_params.get("reserved_slots", "").split()
        # if reserved:
        #     for bus in self.__buses:
        #         if bus.aobject == "pci.0":
        #             for addr in reserved:
        #                 bus.reserve(hex(int(addr)))
        #             break

        return devices

    def _create_launch_security_device(self, launch_security):
        backend = launch_security.get("type")
        props = {"id": launch_security.get("id")}
        props.update(launch_security.get("props"))
        return qdevices.QObject(backend, props)

    def _create_nodefault_device(self):
        return qdevices.QStringDevice("nodefaults", cmdline=" -nodefaults")

    def _create_iommu_device(self, iommu):
        parent_bus = self._get_pci_parent_bus(iommu.get("bus"))
        dev = qdevices.QDevice(iommu["type"], iommu.get("props"), parent_bus=parent_bus)
        if iommu == "intel-iommu":
            set_cmdline_format_by_cfg(
                dev, self._get_cmdline_format_cfg(), "intel_iommu"
            )
        if iommu == "virtio-iommu-pci":
            set_cmdline_format_by_cfg(
                dev, self._get_cmdline_format_cfg(), "virtio_iommu"
            )

        return dev

    def _create_vga_device(self, vga):
        parent_bus = self._get_pci_parent_bus(vga.get("bus"))
        vga_type = vga.get("type")
        if vga_type and vga_type.startswith("VGA-"):
            vga = vga_type.split("VGA-")[-1]
            cmdline = " -vga %s" % vga
            dev = qdevices.QStringDevice(vga_type, cmdline=cmdline, parent_bus=parent_bus)
        else:
            dev = qdevices.QDevice(vga_type, parent_bus=parent_bus)
        set_cmdline_format_by_cfg(dev, self._get_cmdline_format_cfg(), "vga")

        return dev

    def _create_watchdog(self, watchdog):
        devs = []
        watchdog_type = watchdog.get("type")
        if watchdog_type == "itco":
            dev = qdevices.QGlobal("ICH9-LPC", "noreboot", "off")
            devs.append(dev)
        else:
            parent_bus = self._get_pci_parent_bus(watchdog.get("bus"))
            dev = qdevices.QDevice(watchdog_type, parent_bus=parent_bus)
            devs.append(dev)
        cmd = "-watchdog-action %s" % watchdog.get("action")
        devs.append(qdevices.QStringDevice("watchdog_action", cmdline=cmd))
        return devs

    def _create_pci_controller_device(self, pci_controller):
        driver = pci_controller.get("type")
        name = pci_controller["id"]
        props = pci_controller.get("props")
        reserved_slots = ""
        if "reserved_slots" in props and props["reserved_slots"] is not None:
            reserved_slots = props["reserved_slots"]
            del props["reserved_slots"]
        pcic_params = {"id": pci_controller["id"]}
        pcic_params.update(props)

        if driver in ("pcie-root-port", "ioh3420", "x3130-upstream", "x3130"):
            bus_type = "PCIE"
        else:
            bus_type = "PCI"
        parent_bus = [{"aobject": pci_controller.get("bus")}]
        if driver == "x3130":
            bus = qdevices.QPCISwitchBus(name, bus_type, "xio3130-downstream", name)
            driver = "x3130-upstream"
        else:
            if driver == "pci-bridge":  # addr 0x01-0x1f, chasis_nr
                parent_bus.append({"busid": "_PCI_CHASSIS_NR"})
                bus_length = 32
                bus_first_port = 1
            elif driver == "i82801b11-bridge":  # addr 0x1-0x13
                bus_length = 20
                bus_first_port = 1
            elif driver in ("pcie-root-port", "ioh3420"):
                bus_length = 1
                bus_first_port = 0
                parent_bus.append({"busid": "_PCI_CHASSIS"})
            elif driver == "pcie-pci-bridge":
                reserved_slots = "0x0"
                # Unsupported PCI slot 0 for standard hotplug controller.
                # Valid slots are between 1 and 31
                bus_length = 32
                bus_first_port = 1
            else:  # addr = 0x0-0x1f
                bus_length = 32
                bus_first_port = 0
            bus = qdevices.QPCIBus(name, bus_type, name, bus_length, bus_first_port)
        for addr in reserved_slots.split():
            bus.reserve(addr)
        dev = qdevices.QDevice(driver, pcic_params, aobject=name,
                               parent_bus=parent_bus, child_bus=bus)

        set_cmdline_format_by_cfg(dev,
                                  self._get_cmdline_format_cfg(),
                                  "pcic")
        return dev

    def _create_memory(self, memory):
        devs = []

        memory_machine = memory["machine"]
        memory_machine_backend = memory_machine.get("backend")
        memory_backend_type = memory_machine_backend.get("type")
        memory_machine_props = memory_machine_backend.get("props")
        if memory_machine_backend:
            dev = qdevices.Memory(memory_backend_type, memory_machine_props)
            dev.set_param("id", memory_machine_backend.get("id"))
            set_cmdline_format_by_cfg(
                dev, self._get_cmdline_format_cfg(), "mem_devs"
            )
            devs.append(dev)

        options = list()
        options.append(memory_machine["size"])
        if memory_machine.get("max_mem"):
            options.append("maxmem=%s" % memory_machine["max_mem"])
            if memory_machine.get("slots"):
                options.append("slots=%s" % memory_machine["slots"])

        cmdline = "-m %s" % ",".join(map(str, options))
        dev = qdevices.QStringDevice("mem", cmdline=cmdline)
        devs.append(dev)

        return devs

    def _create_memory_devices(self, memory):
        devs = []
        devices = memory.get("devices")
        if devices:
            for device in devices:
                backend = device["backend"]
                dev = qdevices.Memory(backend["type"], backend["props"])
                dev.set_param("id", backend["id"])
                devs.append(dev)

                dev_type = device.get("type")
                if dev_type:
                    if dev_type in ("nvdimm", "pc-dimm"):
                        dev = qdevices.Dimm(params=device["props"],
                                            dimm_type=dev_type)
                        dev.set_param("id", device["id"])
                    elif dev_type in ("virtio-mem-pci", "virtio-mem-device", ):
                        dev = qdevices.QDevice(
                            driver=dev_type,
                            parent_bus=self._get_pci_parent_bus(device["bus"]),
                            params=device["props"],
                        )
                        dev.set_param("id", device["id"])
                    devs.append(dev)

        for dev in devs:
            set_cmdline_format_by_cfg(
                dev, self._get_cmdline_format_cfg(), "mem_devs"
            )

        return devs

    def _create_cpu_devices(self, cpu):
        def __add_smp():
            smp = cpu_topology.get("smp")
            vcpu_maxcpus = cpu_topology.get("maxcpus")
            vcpu_cores = cpu_topology.get("cores")
            vcpu_threads = cpu_topology.get("threads")
            vcpu_dies = cpu_topology.get("dies")
            vcpu_clusters = cpu_topology.get("clusters")
            vcpu_drawers = cpu_topology.get("drawers")
            vcpu_books = cpu_topology.get("books")
            vcpu_sockets = cpu_topology.get("sockets")

            smp_str = " -smp %d" % smp
            if vcpu_maxcpus:
                smp_str += ",maxcpus=%s" % vcpu_maxcpus
            if vcpu_cores:
                smp_str += ",cores=%s" % vcpu_cores
            if vcpu_threads:
                smp_str += ",threads=%s" % vcpu_threads
            if vcpu_dies:
                smp_str += ",dies=%s" % vcpu_dies
            if vcpu_clusters:
                smp_str += ",clusters=%s" % vcpu_clusters
            if vcpu_drawers:
                smp_str += ",drawers=%s" % vcpu_drawers
            if vcpu_books:
                smp_str += ",books=%s" % vcpu_books
            if vcpu_sockets:
                smp_str += ",sockets=%s" % vcpu_sockets
            return smp_str

        def __add_cpu_flags():
            cmd = " -cpu '%s'" % cpu_info["model"]
            if cpu_info.get("vender"):
                cmd += ',vendor="%s"' % cpu_info.get("vender")
            if cpu_info.get("flags"):
                if not cpu_info.get("flags").startswith(","):
                    cmd += ","
                cmd += "%s" % cpu_info.get("flags")
            if cpu_info.get("family"):
                cmd += ",family=%s" % cpu_info.get("family")
            return cmd

        devs = []

        cpu_topology = cpu.get("topology")
        dev = qdevices.QStringDevice("smp", cmdline=__add_smp())
        devs.append(dev)

        cpu_info = cpu.get("info")
        dev = qdevices.QStringDevice("cpu", cmdline=__add_cpu_flags())
        devs.append(dev)

        devices = cpu.get("devices")
        if devices:
            for device in devices:
                dev = qdevices.QCPUDevice(
                    devices.get("type"),
                    device.get("enable"),
                    params=device.get("props"),
                    parent_bus=self._get_pci_parent_bus(device.get("bus")))
                devs.append(dev)
            else:
                raise ValueError("Unsupported CPU device type")

        return devs

    def _create_soundcard_device(self, soundcard):
        devs = []
        soudcard_type = soundcard.get("type")
        parent_bus = self._get_pci_parent_bus(soundcard["bus"])
        if soudcard_type.startswith("SND-"):
            devs.append(qdevices.QStringDevice(soudcard_type, parent_bus=parent_bus))
        else:
            if soudcard_type == "intel-hda":
                dev = qdevices.QDevice(soudcard_type, parent_bus=parent_bus)
                set_cmdline_format_by_cfg(
                    dev, self._get_cmdline_format_cfg(), "soundcards"
                )
                devs.append(dev)
                dev = qdevices.QDevice("hda-duplex")
            elif soudcard_type in ["ES1370", "AC97"]:
                dev = qdevices.QDevice(soudcard_type, parent_bus=parent_bus)
            else:
                dev = qdevices.QDevice(soudcard_type, parent_bus=parent_bus)
            set_cmdline_format_by_cfg(
                dev, self._get_cmdline_format_cfg(), "soundcards"
            )
            devs.append(dev)
        return devs

    def _create_monitor_device(self, monitor):
        devs = []

        monitor_id = monitor.get("id")
        monitor_type = monitor.get("type")
        monitor_props = monitor.get("props")
        monitor_backend = monitor.get("backend")

        if not self._devices.has_option("chardev"):
            filename = monitor_props.get("filename")
            if monitor_type == "qmp":
                cmd = " -qmp unix:'%s',server,nowait" % filename
            else:
                # The monitor type is "hmp"
                cmd = " -monitor unix:'%s',server,nowait" % filename
            dev = qdevices.QStringDevice("QMP-%s" % monitor_id, cmdline=cmd)
            set_cmdline_format_by_cfg(
                dev, self._get_cmdline_format_cfg(), "monitors"
            )
            devs.append(dev)

        else:
            chardev_id = monitor_backend.get("id")
            # convert the monitor_backend_props to Params mandatory.
            chardev_param = Params(monitor_backend.get("props"))
            chardev_param["id"] = chardev_id
            char_device = qdevices.CharDevice(chardev_param, chardev_id)
            set_cmdline_format_by_cfg(
                char_device, self._get_cmdline_format_cfg(), "monitors"
            )
            devs.append(char_device)

            cmd = " -mon chardev=%s,mode=%s" % (chardev_id, monitor_props["mode"])
            dev = qdevices.QStringDevice("QMP-%s" % monitor_id, cmdline=cmd)
            set_cmdline_format_by_cfg(
                dev, self._get_cmdline_format_cfg(), "monitors"
            )
            devs.append(dev)

        return devs

    def _create_panic_device(self, panic):
        parent_bus = self._get_pci_parent_bus(panic.get("bus"))
        params = panic.get("props", {})
        dev = qdevices.QDevice(panic["type"], params=params, parent_bus=parent_bus)
        dev.set_param("id", panic.get("id"), dynamic=True)
        set_cmdline_format_by_cfg(
            dev, self._get_cmdline_format_cfg(), "pvpanic"
        )
        return dev

    def _create_serial_device(self, serial, count):
        def __get_serial_console_filename(name):
            if name:
                return os.path.join(
                    data_dir.get_tmp_dir(),
                    "serial-%s-%s" % (name, self._driver_id)
                )
            return os.path.join(data_dir.get_tmp_dir(),
                                "serial-%s" % self._driver_id)

        devs = []

        serial_type = serial["type"]
        serial_id = serial["id"]
        serial_props = serial["props"]
        machine_type = self._params["machine"]["type"]

        backend = serial.get("backend")
        backend_props = backend.get("props")
        serial_filename = backend_props.get("path")
        if serial_filename:
            serial_dirname = os.path.dirname(serial_filename)
            if not os.path.isdir(serial_dirname):
                os.makedirs(serial_dirname)
        else:
            serial_filename = __get_serial_console_filename(serial_id)

        backend_props["path"] = serial_filename

        # Arm lists "isa-serial" as supported but can't use it,
        # fallback to "-serial"
        legacy_cmd = " -serial unix:'%s',server=on,wait=off" % serial_filename
        legacy_dev = qdevices.QStringDevice("SER-%s" % serial_id, cmdline=legacy_cmd)
        arm_serial = serial_type == "isa-serial" and "arm" in machine_type
        if (
            arm_serial
            or not self._devices.has_option("chardev")
            or not self._devices.has_device(serial_type)
        ):
            devs.append(legacy_dev)
            return devs

        chardev_id = f"chardev_{serial_id}"

        # FIXME: convert to Params
        params = Params()
        for k, v in backend_props.items():
            if k == "port" and isinstance(v, (list, tuple)):
                host = backend_props.get("host")
                free_ports = utils_misc.find_free_ports(
                    v[0], v[1], len(self._params.get("serials")), host)
                params[k] = free_ports[count]
            params[k] = v
        params["id"] = chardev_id

        backend = serial["backend"]["type"]
        if backend in [
            "unix_socket",
            "file",
            "pipe",
            "serial",
            "tty",
            "parallel",
            "parport",
        ]:
            if backend == "pipe":
                filename = params.get("path")
                process.system("mkfifo %s" % filename)

        dev = qdevices.CharDevice(params, chardev_id)
        devs.append(dev)

        serial_props["id"] = serial_id
        bus = serial.get("bus")
        bus_type = None
        if serial_type.startswith("virt"):
            if "-mmio" in machine_type:
                controller_suffix = "device"
            elif machine_type.startswith("s390"):
                controller_suffix = "ccw"
            else:
                controller_suffix = "pci"
            bus_type = "virtio-serial-%s" % controller_suffix

        if serial_type.startswith("virt"):
            bus_params = serial_props.copy()
            if bus_params.get("name"):
                del bus_params["name"]
                del bus_params["id"]

            if not bus or bus == "<new>":
                if bus_type == "virtio-serial-device":
                    pci_bus = {"type": "virtio-bus"}
                elif bus_type == "virtio-serial-ccw":
                    pci_bus = None
                else:
                    pci_bus = {"aobject": "pci.0"}
                if bus != "<new>":
                    bus = self._devices.get_first_free_bus(
                        {"type": "SERIAL", "atype": bus_type},
                        [None, serial_props.get("nr")]
                    )
                #  Multiple virtio console devices can't share a single bus
                if bus is None or bus == "<new>" or serial_type == "virtconsole":
                    _hba = bus_type.replace("-", "_") + "%s"
                    bus = self._devices.idx_of_next_named_bus(_hba)
                    bus = self._devices.list_missing_named_buses(
                        _hba, "SERIAL", bus + 1)[-1]
                    LOG.debug("list missing named bus: %s", bus)
                    bus_params["id"] = bus
                    devs.append(
                        qdevices.QDevice(
                            bus_type,
                            bus_params,
                            bus,
                            pci_bus,
                            qdevices.QSerialBus(bus, bus_type, bus),
                        )
                    )
                else:
                    bus = bus.busid
            dev = qdevices.QDevice(
                serial_type, serial_props, parent_bus={"busid": bus})

        elif serial_type.startswith("pci"):
            bus = self._get_pci_parent_bus(serial["bus"])
            dev = qdevices.QDevice(serial_type, {"id": serial_id}, parent_bus=bus)

        else:  # none virtio type, generate serial device directly
            dev = qdevices.QDevice(serial_type, {"id": serial_id})
            # Workaround for console issue, details:
            # http://lists.gnu.org/archive/html/qemu-ppc/2013-10/msg00129.html
            if (
                    "ppc" in self._params.get("os").get("arch")
                    and serial_type == "spapr-vty"
            ):
                reg = 0x30000000 + 0x1000 * count
                dev.set_param("reg", reg)

        dev.set_param("chardev", chardev_id)
        devs.append(dev)

        self._serials[serial_id] = {"filename": serial_filename}

        return devs

    def _create_rng_device(self, rng):
        devs = []

        rng_type = rng.get("type")
        if rng_type == "pci":
            dev_type = "virtio-rng-pci"
            parent_bus = self._get_pci_parent_bus(rng["bus"])
        elif rng_type == "ccw":
            dev_type = "virtio-rng-ccw"
            parent_bus = None
        else:
            raise NotImplementedError(rng_type)

        rng_dev = qdevices.QDevice(dev_type, rng["props"], parent_bus=parent_bus)
        rng_dev.set_param("id", rng["id"])

        rng_backend = rng.get("backend")
        if self._devices.has_device(dev_type):
            if rng_backend:
                if rng_backend.get("type") == "builtin":
                    backend_type = "rng-builtin"
                elif rng_backend.get("type") == "random":
                    backend_type = "rng-random"
                elif rng_backend.get("type") == "egd":
                    backend_type = "rng-egd"
                else:
                    raise NotImplementedError

                rng_backend_props = rng_backend.get("props")
                rng_backend_chardev = None
                if rng_backend_props.get("chardev"):
                    rng_backend_chardev = rng_backend_props.pop("chardev")
                rng_backend_dev = qdevices.QObject(backend_type, rng_backend_props)
                rng_backend_dev.set_param("id", rng_backend["id"])

                if rng_backend_chardev:
                    char_id = rng_backend_chardev.get("id")
                    rng_chardev = qdevices.QCustomDevice(
                        dev_type="chardev",
                        params=rng_backend_chardev.get("props"),
                        backend=rng_backend_chardev.get("type"),
                    )
                    rng_chardev.set_param("id", char_id)
                    devs.append(rng_chardev)
                    rng_backend_dev.set_param("chardev", rng_chardev.get_qid())

                devs.append(rng_backend_dev)

                rng_dev.set_param("rng", rng_backend_dev.get_qid())
            devs.append(rng_dev)

        return devs

    def _create_debug_device(self, debug):
        devs = []
        debug_type = debug.get("type")

        if debug_type == "isa-debugcon":
            if not self._devices.has_device(debug_type):
                cmd = ""
            else:
                default_id = "seabioslog_id_%s" % self._driver_id
                filename = os.path.join(
                    data_dir.get_tmp_dir(), "seabios-%s" % self._driver_id
                )
                cmd = f" -chardev socket,id={default_id},path={filename},server=on,wait=off"
                cmd += f" -device isa-debugcon,chardev={default_id},iobase=0x402"
            dev = qdevices.QStringDevice("isa-log", cmdline=cmd)
            devs.append(dev)

        elif debug_type == "anaconda_log":
            chardev_id = "anacondalog_chardev_%s" % self._params["uuid"]
            vioser_id = "anacondalog_vioser_%s" % self._params["uuid"]
            filename = os.path.join(
                data_dir.get_tmp_dir(), "anaconda-%s" % self.instance
            )
            self.logs["anaconda"] = filename
            dev = qdevices.QCustomDevice("chardev", backend="backend")
            dev.set_param("backend", "socket")
            dev.set_param("id", chardev_id)
            dev.set_param("path", filename)
            dev.set_param("server", "on")
            dev.set_param("wait", "off")
            devs.append(dev)

            machine_type = self._params["machine"]["type"]
            if "-mmio:" in machine_type:
                dev = qdevices.QDevice("virtio-serial-device")
            elif machine_type.startswith("s390"):
                dev = qdevices.QDevice("virtio-serial-ccw")
            else:
                parent_bus = self._get_pci_parent_bus(debug["bus"])
                dev = qdevices.QDevice("virtio-serial-pci", parent_bus=parent_bus)
            dev.set_param("id", vioser_id)
            devs.append(dev)
            dev = qdevices.QDevice("virtserialport")
            dev.set_param("bus", "%s.0" % vioser_id)
            dev.set_param("chardev", chardev_id)
            dev.set_param("name", "org.fedoraproject.anaconda.log.0")
            devs.append(dev)
        else:
            raise NotImplementedError(debug_type)

        return devs

    def _create_usb_controller_device(self, controller):
        usb_id = controller.get("id")
        usb_type = controller.get("type")
        pci_bus = self._get_pci_parent_bus(controller["bus"])
        max_ports = controller.get("max_ports", 6)
        usb = qdevices.QDevice(
            usb_type,
            {},
            usb_id,
            pci_bus,
            qdevices.QUSBBus(max_ports, "%s.0" % usb_id, usb_type, usb_id),
        )

        devs = [usb]
        usb.set_param("id", usb_id)
        usb.set_param("masterbus", controller.get("masterbus"))
        usb.set_param("multifunction", controller.get("multifunction"))
        usb.set_param("firstport", controller.get("firstport"))
        usb.set_param("freq", controller.get("freq"))
        usb.set_param("addr", controller.get("addr"))
        if usb_type == "ich9-usb-ehci1":
            usb.set_param("addr", "1d.7")
            usb.set_param("multifunction", "on")
            if arch.ARCH in ("ppc64", "ppc64le"):
                for i in xrange(2):
                    devs.append(qdevices.QDevice("pci-ohci", {}, usb_id))
                    devs[-1].parent_bus = pci_bus
                    devs[-1].set_param("id", "%s.%d" % (usb_id, i))
                    devs[-1].set_param("multifunction", "on")
                    devs[-1].set_param("masterbus", "%s.0" % usb_id)
                    # current qdevices doesn't support x.y addr. Plug only
                    # the 0th one into this representation.
                    devs[-1].set_param("addr", "1d.%d" % (3 * i))
                    devs[-1].set_param("firstport", 3 * i)
            else:
                for i in xrange(3):
                    devs.append(
                        qdevices.QDevice("ich9-usb-uhci%d" % (i + 1), {}, usb_id)
                    )
                    devs[-1].parent_bus = pci_bus
                    devs[-1].set_param("id", "%s.%d" % (usb_id, i))
                    devs[-1].set_param("multifunction", "on")
                    devs[-1].set_param("masterbus", "%s.0" % usb_id)
                    # current qdevices doesn't support x.y addr. Plug only
                    # the 0th one into this representation.
                    devs[-1].set_param("addr", "1d.%d" % (2 * i))
                    devs[-1].set_param("firstport", 2 * i)
        for dev in devs:
            set_cmdline_format_by_cfg(dev, self._get_cmdline_format_cfg(),
                                      "usbs")

        return devs

    def _create_usb_device(self, usb):
        usb_type = usb.get("type")
        usb_id = usb.get("id")
        usb_bus = usb.get("bus")
        usb_props = usb.get("props")
        usb_name = usb_id.split("usb-")[-1]

        if self._devices.has_option("device"):
            dev = qdevices.QDevice(usb_type, params=usb_props, aobject=usb_name)
            dev.parent_bus += ({"type": usb_bus},)
        else:
            if "tablet" in usb_type:
                dev = qdevices.QStringDevice(
                    usb_type, cmdline="-usbdevice %s" % usb_name
                )
            else:
                dev = qdevices.QStringDevice(usb_type)
        set_cmdline_format_by_cfg(dev, self._get_cmdline_format_cfg(), "usbs")
        return dev

    def _create_iothread_device(self, iothread):
        dev = qdevices.QIOThread(iothread_id=iothread["id"], params=iothread["props"])

        return dev

    def _create_throttle_group_device(self, throttle_group):
        dev = qdevices.QThrottleGroup(throttle_group["id"], throttle_group["props"])
        return dev

    def _create_disk_devices(self, disk):

        def define_hbas(
            qtype,
            atype,
            bus,
            unit,
            port,
            qbus,
            pci_bus,
            iothread,
            addr_spec=None,
            num_queues=None,
            bus_props={},
        ):
            """
            Helper for creating HBAs of certain type.
            """
            devices = []
            # AHCI uses multiple ports, id is different
            if qbus == qdevices.QAHCIBus:
                _hba = "ahci%s"
            else:
                _hba = atype.replace("-", "_") + "%s.0"  # HBA id
            _bus = bus
            if bus is None:
                bus = self._devices.get_first_free_bus(
                    {"type": qtype, "atype": atype}, [unit, port]
                )
                if bus is None:
                    bus = self._devices.idx_of_next_named_bus(_hba)
                else:
                    bus = bus.busid
            if isinstance(bus, int):
                for bus_name in self._devices.list_missing_named_buses(_hba, qtype, bus + 1):
                    _bus_name = bus_name.rsplit(".")[0]
                    bus_params = {"id": _bus_name, "driver": atype}
                    if num_queues is not None and int(num_queues) > 1:
                        bus_params["num_queues"] = num_queues
                    bus_params.update(bus_props)
                    if addr_spec:
                        dev = qdevices.QDevice(
                            params=bus_params,
                            parent_bus=pci_bus,
                            child_bus=qbus(
                                busid=bus_name,
                                bus_type=qtype,
                                addr_spec=addr_spec,
                                atype=atype,
                            ),
                        )
                    else:
                        dev = qdevices.QDevice(
                            params=bus_params,
                            parent_bus=pci_bus,
                            child_bus=qbus(busid=bus_name),
                        )
                    if iothread:
                        try:
                            _iothread = self._devices.allocate_iothread(iothread, dev)
                        except TypeError:
                            pass
                        else:
                            if _iothread and _iothread not in self:
                                devices.append(_iothread)
                    devices.append(dev)
                bus = _hba % bus
            if qbus == qdevices.QAHCIBus and unit is not None:
                bus += ".%d" % unit
            # If bus was not set, don't set it, unless the device is
            # a spapr-vscsi device.
            elif _bus is None and "spapr_vscsi" not in _hba:
                bus = None
            return devices, bus, {"type": qtype, "atype": atype}

        devices = []

        name = disk.get("id")
        source = disk.get("source")
        device = disk.get("device")
        device_props = device.get("props")
        device_bus = device.get("bus")
        iothread = None  # FIXME: skip this at the moment

        # Create the HBA devices
        if device_bus:
            bus_type = device_bus.get("type")
            parent_bus = device_bus.get("bus")
            pci_bus = self._get_pci_parent_bus(parent_bus)
            device_bus_props = device_bus.get("props")
            bus = device_props.get("bus")
            unit = device_props.get("unit")
            port = device_props.get("port")
            num_queues = device_bus_props.get("num_queues")
            if "num_queues" in device_bus_props:
                del device_bus_props["num_queues"]

            if device["type"] == "ide":
                bus = unit
                dev_parent = {"type": "IDE", "atype": bus_type}
            elif device["type"] == "ahci":
                devs, bus, dev_parent = define_hbas(
                    "IDE", "ahci", bus, unit, port, qdevices.QAHCIBus, pci_bus,
                    iothread
                )
                devices.extend(devs)
            elif device["type"].startswith("scsi-"):
                qbus = qdevices.QSCSIBus
                addr_spec = device_bus_props.get("addr_spec")
                if "addr_spec" in device_bus_props:
                    del device_bus_props["addr_spec"]
                devs, bus, dev_parent = define_hbas("SCSI", bus_type, bus, unit, port,
                                                    qbus, pci_bus, iothread, addr_spec,
                                                    num_queues, device_bus_props)
                devices.extend(devs)

        # create the driver or block node device
        if source:
            protocol_node = source
            protocol_node_type = protocol_node.get("type")
            protocol_node_props = protocol_node.get("props")
            if protocol_node_type == qdevices.QBlockdevProtocolFile.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolFile
            elif protocol_node_type == qdevices.QBlockdevProtocolNullCo.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolNullCo
            elif protocol_node_type == qdevices.QBlockdevProtocolISCSI.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolISCSI
            elif protocol_node_type == qdevices.QBlockdevProtocolRBD.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolRBD
            elif protocol_node_type == qdevices.QBlockdevProtocolGluster.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolGluster
            elif protocol_node_type == qdevices.QBlockdevProtocolNBD.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolNBD
            elif protocol_node_type == qdevices.QBlockdevProtocolNVMe.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolNVMe
            elif protocol_node_type == qdevices.QBlockdevProtocolSSH.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolSSH
            elif protocol_node_type == qdevices.QBlockdevProtocolHTTPS.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolHTTPS
            elif protocol_node_type == qdevices.QBlockdevProtocolHTTP.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolHTTP
            elif protocol_node_type == qdevices.QBlockdevProtocolFTPS.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolFTPS
            elif protocol_node_type == qdevices.QBlockdevProtocolFTP.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolFTP
            elif protocol_node_type == qdevices.QBlockdevProtocolVirtioBlkVhostVdpa.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolVirtioBlkVhostVdpa
            elif protocol_node_type == qdevices.QBlockdevProtocolHostDevice.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolHostDevice
            elif protocol_node_type == qdevices.QBlockdevProtocolBlkdebug.TYPE:
                protocol_cls = qdevices.QBlockdevProtocolBlkdebug
            else:
                raise ValueError("Unsupported protocol node type: %s" % protocol_node_type)
            protocol_node = protocol_cls(name)
            devices.append(protocol_node)
            top_node = protocol_node

            format_node = source.get("format")
            if format_node:
                format_node_type = format_node.get("type")
                format_node_props = format_node.get("props")
                if format_node_type == qdevices.QBlockdevFormatQcow2.TYPE:
                    format_cls = qdevices.QBlockdevFormatQcow2
                elif format_node_type == qdevices.QBlockdevFormatRaw.TYPE:
                    format_cls = qdevices.QBlockdevFormatRaw
                elif format_node_type == qdevices.QBlockdevFormatLuks.TYPE:
                    format_cls = qdevices.QBlockdevFormatLuks
                else:
                    raise ValueError("Unsupported format node type: %s" % format_node_type)
                format_node = format_cls(source.get("id"))
                format_node.add_child_node(protocol_node)
                devices.append(format_node)
                top_node = format_node

            for key, value in protocol_node_props.items():
                if key not in protocol_node.params:
                    protocol_node.set_param(key, value)

            if format_node_props:
                for key, value in format_node_props.items():
                    if key not in format_node.params:
                        format_node.set_param(key, value)

            if top_node is not protocol_node:
                top_node.set_param("file", protocol_node.get_qid())

        # create the devices
        if device:
            device_type = device.get("type")
            name = device.get("id")
            params = device.get("props")
            params["bus"] = bus

            dev = qdevices.QDevice(device_type, params, name)
            dev.parent_bus += ({"busid": "drive_%s" % name}, dev_parent)
            dev.set_param("id", name)
            devices.append(dev)

        for device in devices:
            set_cmdline_format_by_cfg(device, self._get_cmdline_format_cfg(),
                                      "images")
        return devices

    def _create_filesystem_device(self, filesystem):
        fs_type = filesystem["type"]
        fs_source = filesystem["source"]
        fs_source_type = fs_source["type"]
        fs_source_props = fs_source["props"]
        fs_target = filesystem["target"]
        fs_driver = filesystem["driver"]
        fs_driver_type = fs_driver["type"]
        fs_driver_props = fs_driver["props"]

        machine_type = self._params["machine"]["type"]
        qbus_type = "PCI"
        if machine_type.startswith("q35") or machine_type.startswith("arm64"):
            qbus_type = "PCIE"

        devices = []
        if fs_driver_type == "virtio-fs":
            sock_path = os.path.join(
                data_dir.get_tmp_dir(),
                "-".join((self.vmname, filesystem["id"], "virtiofsd.sock")),
            )
            vfsd = qdevices.QVirtioFSDev(
                filesystem["id"],
                fs_driver_props["binary"],
                sock_path,
                fs_source_props["path"],
                fs_driver_props["options"],
                fs_driver_props["debug_mode"],
            )
            devices.append(vfsd)

            char_params = Params()
            char_params["backend"] = "socket"
            char_params["id"] = "char_%s" % vfsd.get_qid()
            sock_bus = {"busid": sock_path}
            char = qdevices.CharDevice(char_params, parent_bus=sock_bus)
            char.set_aid(vfsd.get_aid())
            devices.append(char)

            qdriver = "vhost-user-fs"
            if "-mmio:" in machine_type:
                qdriver += "-device"
                qbus_type = "virtio-bus"
            elif machine_type.startswith("s390"):
                qdriver += "-ccw"
                qbus_type = "virtio-bus"
            else:
                qdriver += "-pci"

            bus = filesystem["bus"]
            if bus is None:
                bus = {"type": qbus_type}

            dev_params = {
                "id": "vufs_%s" % vfsd.get_qid(),
                "chardev": char.get_qid(),
                "tag": fs_target,
            }
            dev_params.update(fs_driver_props)
            vufs = qdevices.QDevice(qdriver, params=fs_driver_props, parent_bus=bus)
            vufs.set_aid(vfsd.get_aid())
            devices.append(vufs)
        else:
            raise ValueError("unsupported filesystem driver type")
        return devices

    def _create_net_device(self, net):
        return

    def _create_vsock_device(self, vsock):
        vsock_params = vsock.get("props", {})
        vsock_params["id"] = vsock.get("id")
        bus = self._get_pci_parent_bus(vsock["bus"])
        dev = qdevices.QDevice(vsock.get("type"), vsock_params, parent_bus=bus)
        set_cmdline_format_by_cfg(
            dev, self._get_cmdline_format_cfg(), "vsocks"
        )
        return dev

    def _create_os_device(self, os):
        def __add_boot(opts):
            machine_type = self._params["machine"]["type"]
            if machine_type.startswith("arm") or machine_type.startswith("riscv"):
                LOG.warn(
                    "-boot on %s is usually not supported, use " "bootindex instead.",
                    machine_type,
                )
                return ""
            if machine_type.startswith("s390"):
                LOG.warn("-boot on s390x only support boot strict=on")
                return "-boot strict=on"
            cmd = " -boot"
            options = []
            for p in list(opts.keys()):
                pattern = "boot .*?(\[,?%s=(.*?)\]|\s+)" % p
                if self._devices.has_option(pattern):
                    option = opts[p]
                    if option is not None:
                        options.append("%s=%s" % (p, option))
            if self._devices.has_option("boot \[a\|c\|d\|n\]"):
                cmd += " %s" % opts["once"]
            elif options:
                cmd += " %s" % ",".join(options)
            else:
                cmd = ""
            return cmd

        devs = []
        kernel = os.get("kernel")
        if kernel:
            kernel = utils_misc.get_path(data_dir.get_data_dir(), kernel)
            devs.append(
                qdevices.QStringDevice("kernel", cmdline=" -kernel '%s'" % kernel)
            )

        kernel_params = os.get("cmdline")
        if kernel_params:
            devs.append(
                qdevices.QStringDevice(
                    "kernel-params", cmdline=" -append '%s'" % kernel_params
                )
            )

        initrd = os.get("initrd")
        if initrd:
            initrd = utils_misc.get_path(data_dir.get_data_dir(), initrd)
            devs.append(
                qdevices.QStringDevice("initrd", cmdline=" -initrd '%s'" % initrd)
            )

        boot = os.get("boot")
        if boot:
            if self._devices.has_option("boot"):
                cmd = __add_boot(boot)
                devs.append(qdevices.QStringDevice("bootmenu", cmdline=cmd))

        bios = os.get("bios")
        if bios:
            devs.append(qdevices.QStringDevice("bios", cmdline="-bios %s" % bios))

        return devs

    def _create_graphics_device(self, graphic):
        def add_sdl(devices):
            if devices.has_option("sdl"):
                return " -sdl"
            else:
                return ""

        def add_nographic():
            return " -nographic"

        graphic_type = graphic.get("type")
        graphic_props = graphic.get("props")
        cmd = ""
        if graphic_type == "vnc":
            free_port = utils_misc.find_free_port(5900, 6900, sequent=True)
            vnc_port = graphic_props.get("port")
            if vnc_port:
                del graphic_props["port"]
            else:
                vnc_port = free_port
            cmd = " -vnc :%d" % (vnc_port - 5900)
            password = graphic_props.get("password")
            if password:
                del graphic_props["password"]
                if password == "yes":
                    cmd += ",password"
            for k, v in graphic_props.items():
                cmd += ",%s" % f"{k}={v}"
        elif graphic_type == "sdl":
            if self._devices.has_option("sdl"):
                cmd = " -sdl"
        elif graphic_type == "nographic":
            cmd = ""
        else:
            raise ValueError(f"unsupported graphic type {graphic_type}")

        return qdevices.QStringDevice("display", cmdline=cmd)

    def _create_rtc_device(self, rtc):
        if self._devices.has_option("rtc"):
            base = rtc["base"]
            clock = rtc["clock"]
            driftfix = rtc["driftfix"]
            cmd = f"-rtc base={base},clock={clock},driftfix={driftfix}"
            return qdevices.QStringDevice("rtc", cmdline=cmd)

    def _create_tpm_device(self, tpm):
        def _handle_log(line):
            try:
                log_filename = os.path.join(
                    LOG_DIR, "%s_%s_swtpm_setup.log" % (self._instance_id, tpm_id))
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

            LOG.info("<Instance: %s> Running TPM emulator setup command: %s",
                     self._instance_id, setup_cmd)
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
        tpm_dev = qdevices.QCustomDevice(
            "tpmdev", tpm_params, tpm_id, backend="backend"
        )
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
            set_cmdline_format_by_cfg(dev, self._get_cmdline_format_cfg(),
                                      "tpm")

        return devs

    def _create_input_device(self, input):
        input_type = input.get("type")
        input_bus = input.get("bus")
        machine_type = self._params["machine"]["type"]
        dev = None

        drv_map = {
            "mouse": "virtio-mouse",
            "keyboard": "virtio-keyboard",
            "tablet": "virtio-tablet",
        }
        driver = drv_map.get(input_type)

        if "-mmio:" in machine_type:
            driver += "-device"
        elif machine_type.startswith("s390"):
            driver += "-ccw"
        else:
            driver += "-pci"

        if self._devices.has_device(driver):
            dev = qdevices.QDevice(driver, parent_bus={"type": input_bus})
            dev.set_param("id", "input_%s" % input["id"])
        else:
            LOG.warn("'%s' is not supported by your qemu", driver)

        return dev

    def _create_balloon_device(self, balloon):
        machine_type = self.params.get("machine_type")
        devid = balloon.get("id")
        bus = balloon["bus"]
        if "s390" in machine_type:  # For s390x platform
            model = "virtio-balloon-ccw"
            bus = {"type": bus}
        else:
            model = "virtio-balloon-pci"
        dev = qdevices.QDevice(model, params=balloon.get("props"), parent_bus=bus)
        if devid:
            dev.set_param("id", devid)
        return dev

    def _get_cmdline_format_cfg(self):
        """
        get data from file or input from parameter and then convert data to dict
        :return: style data in dict
        """

        def _file(filepath):
            if not filepath:
                raise ValueError("The filepath is empty!")
            if not os.path.isabs(filepath):
                vt_type = self._params.get("vt_type", "qemu")
                filepath = data_dir.get_backend_cfg_path(vt_type, filepath)
            with open(filepath, "r") as f:
                content = f.read()
            return content

        def _string(content):
            return content

        def _default(dummy):
            return "{}"

        # FIXME: hardcode the qemu cmdline format cfg file path
        self._params["qemu_cmdline_format_cfg"] = "file:/home/libvirt-latest.json"
        handler, value = self._params.get("qemu_cmdline_format_cfg", ":").split(":", 1)
        get_func = {"file": _file, "string": _string, "": _default}
        if handler not in get_func:
            LOG.warning("Unknown qemu cmdline format config...ignoring!")
            handler, value = "", ""
        return json.loads(get_func.get(handler)(value))

    def create_devices(self, spec):
        self._params = json.loads(spec)
        # FIXME: hardcode for the qemu binary path
        self._qemu_binary = "/usr/libexec/qemu-kvm"
        self._devices = qcontainer.DevContainer(self._qemu_binary, self._params["name"])

        cmd = ""
        self._devices.insert(qdevices.QStringDevice("PREFIX", cmdline=cmd))
        self._devices.insert(qdevices.QStringDevice("qemu", cmdline=self._qemu_binary))

        if self._params["preconfig"]:
            self._devices.insert(
                qdevices.QStringDevice("preconfig", cmdline="--preconfig")
            )

        name = self._params["name"]
        self._devices.insert(
            qdevices.QStringDevice("vmname", cmdline=f"-name {name}")
        )

        sandbox = self._params.get("sandbox")
        if sandbox:
            dev = self._create_sandbox_device(sandbox)
            self._devices.insert(dev)

        # FIXME:
        firmware = self._params.get("firmware")
        devs = self._create_firmware_devices(firmware)
        self._devices.insert(devs)

        machine = self._params.get("machine")
        if machine:
            devs = self._create_machine_devices(machine)
            self._devices.insert(devs)

        controllers = self._params.get("controllers")
        if controllers:
            extra_pcie = []
            for controller in controllers:
                controller_type = controller.get("type")
                if controller_type in ("pcie-root-port", "ioh3420",
                                       "x3130-upstream", "x3130",
                                       "pci-bridge", "i82801b11-bridge",
                                       "pcie-pci-bridge", ):
                    name = controller.get("id")
                    # FIXME: workaround to distinguish the extra pci root port
                    if not name.startswith("pcie_extra_root_port_"):
                        dev = self._create_pci_controller_device(controller)
                        self._devices.insert(dev)
                    else:
                        extra_pcie.append(controller)

                    func_0_addr = None
                    extra_port_num = len(extra_pcie)
                    for num, pci_controller in enumerate(extra_pcie):
                        try:
                            root_port = self._create_pci_controller_device(pci_controller)
                            func_num = num % 8
                            if func_num == 0:
                                self._devices.insert(root_port)
                                func_0_addr = root_port.get_param("addr")
                            else:
                                port_addr = "%s.%s" % (func_0_addr, hex(func_num))
                                root_port.set_param("addr", port_addr)
                                self._devices.insert(root_port)
                        except DeviceError:
                            LOG.warning(
                                "No sufficient free slot for extra"
                                " root port, discarding %d of them" % (
                                            extra_port_num - num)
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
                                        "qemu-xhci",):
                    dev = self._create_usb_controller_device(controller)
                    self._devices.insert(dev)

        launch_security = self._params.get("launch_security")
        if launch_security:
            dev = self._create_launch_security_device(launch_security)
            self._devices.insert(dev)

        defaults = self._params.get("defaults")
        if not defaults:
            dev = self._create_nodefault_device()
            self._devices.insert(dev)

        iommu = self._params.get("iommu")
        if iommu:
            dev = self._create_iommu_device(iommu)
            self._devices.insert(dev)

        vga = self._params.get("vga")
        if vga:
            dev = self._create_vga_device(vga)
            self._devices.insert(dev)

        watchdog = self._params.get("watchdog")
        if watchdog:
            dev = self._create_watchdog(watchdog)
            self._devices.insert(dev)

        memory = self._params.get("memory")
        machine_dev = self._devices.get_by_properties({"type": "machine"})[0]
        if memory:
            devs = self._create_memory(memory)
            self._devices.insert(devs)
            for dev in devs:
                if isinstance(dev, qdevices.Memory):
                    machine_dev.set_param("memory-backend", dev.get_qid())

            devs = self._create_memory_devices(memory)
            self._devices.insert(devs)

        cpu = self._params.get("cpu")
        if cpu:
            devs = self._create_cpu_devices(cpu)
            self._devices.insert(devs)

        soundcards = self._params.get("soundcards")
        if soundcards:
            for soundcard in soundcards:
                dev = self._create_soundcard_device(soundcard)
                self._devices.insert(dev)

        monitors = self._params.get("monitors")
        if monitors:
            for monitor in monitors:
                devs = self._create_monitor_device(monitor)
                self._devices.insert(devs)

        panics = self._params.get("panics")
        if panics:
            for panic in panics:
                dev = self._create_panic_device(panic)
                self._devices.insert(dev)

        vmcoreinfo = self._params.get("vmcoreinfo")
        if vmcoreinfo:
            dev = qdevices.QDevice("vmcoreinfo")
            self._devices.insert(dev)

        serials = self._params.get("serials")
        for serial in serials:
            count = 0
            dev = self._create_serial_device(serial, count)
            count += 1
            self._devices.insert(dev)

        rngs = self._params.get("rngs")
        if rngs:
            for rng in rngs:
                dev = self._create_rng_device(rng)
                self._devices.insert(dev)

        debugs = self._params.get("debugs")
        if debugs:
            for debug in debugs:
                dev = self._create_debug_device(debug)
                self._devices.insert(dev)

        # controllers = self._params.get("controllers")
        # if controllers:
        #     for controller in controllers:
        #         dev = self._create_controller_device(controller)
        #         self._devices.insert(dev)

        usbs = self._params.get("usbs")
        if usbs:
            for usb in usbs:
                dev = self._create_usb_device(usb)
                self._devices.insert(dev)

        iothreads = self._params.get("iothreads")
        if iothreads:
            for iothread in iothreads:
                dev = self._create_iothread_device(iothread)
                self._devices.insert(dev)

        throttle_groups = self._params.get("throttle_groups")
        if throttle_groups:
            for throttle_group in throttle_groups:
                dev = self._create_throttle_group_device(throttle_group)
                self._devices.insert(dev)

        disks = self._params.get("disks")
        if disks:
            for disk in disks:
                devs = self._create_disk_devices(disk)
                self._devices.insert(devs)

        filesystems = self._params.get("filesystems")
        if filesystems:
            for filesystem in filesystems:
                dev = self._create_filesystem_device(filesystem)
                self._devices.insert(dev)

        # nets = self._params.get("nets")
        # if nets:
        #     for net in nets:
        #         dev = self._create_net_device(net)
        #         self._devices.insert(dev)

        vsocks = self._params.get("vsocks")
        if vsocks:
            for vsock in vsocks:
                dev = self._create_vsock_device(vsock)
                self._devices.insert(dev)

        os = self._params.get("os")
        if os:
            dev = self._create_os_device(os)
            self._devices.insert(dev)

        graphics = self._params.get("graphics")
        if graphics:
            for graphics in graphics:
                dev = self._create_graphics_device(graphics)
                self._devices.insert(dev)

        rtc = self._params.get("rtc")
        if rtc:
            dev = self._create_rtc_device(rtc)
            self._devices.insert(dev)

        tpms = self._params.get("tpms")
        if tpms:
            for tpm in tpms:
                dev = self._create_tpm_device(tpm)
                self._devices.insert(dev)

        self._devices.insert(qdevices.QStringDevice("kvm", cmdline="-enable-kvm"))

        pm = self._params.get("power_management")
        if pm:
            if pm.get("no_shutdown"):
                if self._devices.has_option("no-shutdown"):
                    self._devices.insert(
                        qdevices.QStringDevice("noshutdown", cmdline="-no-shutdown")
                    )

        inputs = self._params.get("inputs")
        if inputs:
            for input in inputs:
                dev = self._create_input_device(input)
                self._devices.insert(dev)

        balloons = self._params.get("balloons")
        if balloons:
            for balloon in balloons:
                dev = self._create_balloon_device(balloon)
                self._devices.insert(dev)

        keyboard_layout = self._params.get("keyboard_layout")
        if keyboard_layout:
            dev = qdevices.QStringDevice("k", cmdline=keyboard_layout)
            self._devices.insert(dev)

        # set tag for pcic
        for dev in self._devices:
            if dev.get_param("driver", "") in (
                "pcie-root-port",
                "pcie-pci-bridge",
                "pci-bridge",
            ):
                set_cmdline_format_by_cfg(dev, self._get_cmdline_format_cfg(), "pcic")

        return self._devices

    def _incoming_cmd(self, migrate_inc_uri):
        if self._devices.has_option("incoming defer"):
            migrate_inc_uri = "defer"
        incoming_cmd = f" -incoming {migrate_inc_uri}"

        return incoming_cmd

    def make_cmdline(self, migrate_inc_uri=None):
        if migrate_inc_uri:
            self._migrate_inc_uri = migrate_inc_uri
        self._cmdline = self._devices.cmdline()

        if migrate_inc_uri:
            self._cmdline += self._incoming_cmd(migrate_inc_uri)
        return self._cmdline

    def verify_status(self, status):
        """
        Check VM status

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

    def wait_for_status(self, status, timeout, first=0.0, step=1.0, text=None):
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
        self.monitor.cmd("stop")
        self.verify_status("paused")

    def cont(self, timeout=60):
        self.monitor.cmd("cont")
        if timeout:
            if not self.wait_for_status("running", timeout, step=0.1):
                raise virt_vm.VMStatusError(
                    "Failed to enter running status, "
                    "the actual status is %s" % self.monitor.get_status()
                )
        else:
            self.verify_status("running")

    # def parse_migration_parameter(self, virt_parameter, value):
    #     # Translate the virt parameter to the qemu parameter
    #     cmd = "migrate-set-parameters"
    #     if virt_parameter not in PARAMETERS_MAPPING:
    #         raise ValueError("Unsupported virt parameter: %s" % virt_parameter)
    #     parameter = PARAMETERS_MAPPING.get(virt_parameter).get("options")[0]
    #     args = {parameter: value}
    #     return cmd, args
    #
    # def set_migration_parameter(self, monitor_name, virt_parameter, value):
    #     for monitor in self.monitors:
    #         if monitor.name == monitor_name:
    #             cmd, args = self.parse_migration_parameter(monitor,
    #                                                        virt_parameter,
    #                                                        value)
    #             data = (cmd, args)
    #             monitor.execute_data(data, data_format=None)
    #             return True
    #     return False
