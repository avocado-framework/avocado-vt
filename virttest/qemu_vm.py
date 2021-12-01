"""
Utility classes and functions to handle Virtual Machine creation using qemu.

:copyright: 2008-2009, 2014 Red Hat Inc.
"""

from __future__ import division
import time
import os
import logging
import fcntl
import re
import random
import sys
import math
import json
import ast

from functools import partial, reduce
from operator import mul

import aexpect
from aexpect import remote

from avocado.core import exceptions
from avocado.utils import process
from avocado.utils import crypto
from avocado.utils import linux_modules
from avocado.utils.astring import to_text

import six
from six.moves import xrange

from virttest import utils_misc
from virttest import cpu
from virttest import virt_vm
from virttest import test_setup
from virttest import qemu_migration
from virttest import qemu_monitor
from virttest import qemu_virtio_port
from virttest import data_dir
from virttest import utils_net
from virttest import arch
from virttest import storage
from virttest import error_context
from virttest import utils_vsock
from virttest import error_event
from virttest.qemu_devices import qdevices, qcontainer
from virttest.qemu_devices.utils import DeviceError
from virttest.qemu_capabilities import Flags
from virttest.utils_params import Params


# Using as lower capital is not the best way to do, but this is just a
# workaround to avoid changing the entire file.
LOG = logging.getLogger('avocado.' + __name__)


# Taking this as a workaround to avoid getting errors during pickling
# with Python versions prior to 3.7.
if sys.version_info < (3, 7):
    def _picklable_logger(*args, **kwargs):
        return LOG.info(*args, **kwargs)
else:
    _picklable_logger = LOG.info


class QemuSegFaultError(virt_vm.VMError):

    def __init__(self, crash_message):
        virt_vm.VMError.__init__(self, crash_message)
        self.crash_message = crash_message

    def __str__(self):
        return "Qemu crashed: %s" % self.crash_message


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
        return ("QEMU reports it doesn't know migration protocol '%s'. "
                "QEMU output: %s" % (self.protocol, self.output))


class KVMInternalError(virt_vm.VMError):
    pass


class ImageUnbootableError(virt_vm.VMError):

    def __init__(self, name):
        virt_vm.VMError.__init__(self, name)
        self.name = name

    def __str__(self):
        return ("VM '%s' can't bootup from image,"
                " check your boot disk image file." % self.name)


def clean_tmp_files():
    if os.path.isfile(CREATE_LOCK_FILENAME):
        os.unlink(CREATE_LOCK_FILENAME)


CREATE_LOCK_FILENAME = os.path.join(data_dir.get_tmp_dir(),
                                    'avocado-vt-vm-create.lock')


def qemu_proc_term_handler(vm, monitor_exit_status, exit_status):
    """Monitors qemu process unexpected exit.

    Callback function to detect QEMU process non-zero exit status and
    push VMExitStatusError to background error bus.

    :param vm: VM object.
    :param monitor_exit_status: True to push VMUnexpectedExitError instance
        with calltrace to global error event bus.
    :param exit_status: QEMU process exit status.
    """
    for snapshot in vm.devices.temporary_image_snapshots:
        try:
            os.unlink(snapshot)
        except OSError:
            pass
    vm.devices.temporary_image_snapshots.clear()

    if exit_status != 0 and monitor_exit_status:
        try:
            raise virt_vm.VMUnexpectedExitError(vm.name, exit_status)
        except virt_vm.VMUnexpectedExitError:
            error_event.error_events_bus.put(sys.exc_info())


class VM(virt_vm.BaseVM):

    """
    This class handles all basic VM operations.
    """

    MIGRATION_PROTOS = ['rdma', 'x-rdma', 'tcp', 'unix', 'exec', 'fd']

    # By default we inherit all timeouts from the base VM class except...
    CLOSE_SESSION_TIMEOUT = 30
    MIGRATE_TIMEOUT = 2000
    #: By default translate standard and experimental (prefixed with x-)
    #: options according to supported parameters/capabilities. To turn this
    #: off enable this option
    DISABLE_AUTO_X_MIG_OPTS = False

    def __init__(self, name, params, root_dir, address_cache, state=None):
        """
        Initialize the object and set a few attributes.

        :param name: The name of the object
        :param params: A dict containing VM params
                (see method make_create_command for a full description)
        :param root_dir: Base directory for relative filenames
        :param address_cache: A dict that maps MAC addresses to IP addresses
        :param state: If provided, use this as self.__dict__
        """

        if state:
            self.__dict__ = state
        else:
            self.process = None
            self.serial_ports = []
            self.serial_console_log = None
            self.serial_session_device = None
            self.redirs = {}
            self.spice_options = {}
            self.vnc_port = 5900
            self.monitors = []
            self.virtio_ports = []      # virtio_console / virtio_serialport
            self.pci_assignable = None
            self.uuid = None
            self.vhost_threads = []
            self.devices = None
            self.logs = {}
            self.remote_sessions = []
            self.logsessions = {}
            self.deferral_incoming = False

        self.name = name
        self.params = params
        self.root_dir = root_dir
        self.ip_version = self.params.get("ip_version", "ipv4")
        self.address_cache = address_cache
        self.index_in_use = {}
        # This usb_dev_dict member stores usb controller and device info,
        # It's dict, each key is an id of usb controller,
        # and key's value is a list, contains usb devices' ids which
        # attach to this controller.
        # A filled usb_dev_dict may look like:
        # { "usb1" : ["stg1", "stg2", "stg3", "stg4", "stg5", "stg6"],
        #   "usb2" : ["stg7", "stg8"],
        #   ...
        # }
        # This structure can used in usb hotplug/unplug test.
        self.usb_dev_dict = {}
        self.driver_type = 'qemu'
        self.params['driver_type_' + self.name] = self.driver_type
        # virtnet init depends on vm_type/driver_type being set w/in params
        super(VM, self).__init__(name, params)
        # un-overwrite instance attribute, virtnet db lookups depend on this
        if state:
            self.instance = state['instance']
        self.qemu_command = ''
        self.start_time = 0.0
        self.start_monotonic_time = 0.0
        self.last_boot_index = 0
        self.last_driver_index = 0

    @property
    def vcpu_threads(self):
        return self.get_vcpu_pids(debug=False)

    def check_capability(self, capability):
        """
        Check whether the given capability is set in the vm capabilities.

        :param capability: the given capability
        :type capability: qemu_capabilities.Flags
        """
        if self.devices is None:
            raise virt_vm.VMStatusError('Using capabilities before '
                                        'VM being defined')
        return capability in self.devices.caps

    def check_migration_parameter(self, parameter):
        """
        Check whether the given migration parameter is set in the vm migration
        parameters.

        :param parameter: the given migration parameter
        :type parameter: qemu_capabilities.MigrationParams
        """
        if self.devices is None:
            raise virt_vm.VMStatusError('Using migration parameters before '
                                        'VM being defined')
        return parameter in self.devices.mig_params

    def verify_alive(self):
        """
        Make sure the VM is alive and that the main monitor is responsive.

        :raise VMDeadError: If the VM is dead
        :raise: Various monitor exceptions if the monitor is unresponsive
        """
        self.verify_disk_image_bootable()
        self.verify_userspace_crash()
        self.verify_kernel_crash()
        self.verify_illegal_instruction()
        self.verify_kvm_internal_error()
        try:
            virt_vm.BaseVM.verify_alive(self)
            if self.monitor:
                self.monitor.verify_responsive()
        except virt_vm.VMDeadError:
            raise virt_vm.VMDeadError(self.process.get_status(),
                                      self.process.get_output())

    def is_alive(self):
        """
        Return True if the VM is alive and its monitor is responsive.
        """
        return not self.is_dead() and (not self.catch_monitor or
                                       self.catch_monitor.is_responsive())

    def is_dead(self):
        """
        Return True if the qemu process is dead.
        """
        return not self.process or not self.process.is_alive()

    def is_paused(self):
        """
        Return True if the qemu process is paused (stopped)
        """
        if self.is_dead():
            return False
        try:
            self.verify_status("paused")
            return True
        except virt_vm.VMStatusError:
            return False

    def is_panicked(self):
        """
        Return True if the qemu process is panicked
        """
        if self.is_dead():
            return False
        try:
            self.verify_status("guest-panicked")
            return True
        except virt_vm.VMStatusError:
            return False

    def verify_status(self, status):
        """
        Check VM status

        :param status: Optional VM status, 'running' or 'paused'
        :raise VMStatusError: If the VM status is not same as parameter
        """
        if not self.monitor.verify_status(status):
            raise virt_vm.VMStatusError('Unexpected VM status: "%s"' %
                                        self.monitor.get_status())

    def verify_userspace_crash(self):
        """
        Verify if the userspace component (qemu) crashed.
        """
        if "(core dumped)" in self.process.get_output():
            for line in self.process.get_output().splitlines():
                if "(core dumped)" in line:
                    raise QemuSegFaultError(line)

    def verify_kvm_internal_error(self):
        """
        Verify KVM internal error.
        """
        if "KVM internal error." in self.process.get_output():
            out = self.process.get_output()
            out = out[out.find("KVM internal error."):]
            raise KVMInternalError(out)

    def verify_disk_image_bootable(self):
        if self.params.get("image_verify_bootable") == "yes":
            pattern = self.params.get("image_unbootable_pattern")
            if not pattern:
                raise virt_vm.VMConfigMissingError(self.name,
                                                   "image_unbootable_pattern")
            try:
                seabios_log = self.logsessions['seabios'].get_output()
                if re.search(pattern, seabios_log, re.S):
                    LOG.error("Can't boot guest from image.")
                    # Set 'shutdown_command' to None to force autotest
                    # shuts down guest with monitor.
                    self.params["shutdown_command"] = None
                    raise ImageUnbootableError(self.name)
            except KeyError:
                pass

    def clone(self, name=None, params=None, root_dir=None, address_cache=None,
              copy_state=False):
        """
        Return a clone of the VM object with optionally modified parameters.
        The clone is initially not alive and needs to be started using create().
        Any parameters not passed to this function are copied from the source
        VM.

        :param name: Optional new VM name
        :param params: Optional new VM creation parameters
        :param root_dir: Optional new base directory for relative filenames
        :param address_cache: A dict that maps MAC addresses to IP addresses
        :param copy_state: If True, copy the original VM's state to the clone.
                Mainly useful for make_create_command().
        """
        if name is None:
            name = self.name
        if params is None:
            params = self.params.copy()
        if root_dir is None:
            root_dir = self.root_dir
        if address_cache is None:
            address_cache = self.address_cache
        if copy_state:
            state = self.__dict__.copy()
        else:
            state = None
        return VM(name, params, root_dir, address_cache, state)

    def get_serial_console_filename(self, name=None):
        """
        Return the serial console filename.

        :param name: The serial port name.
        """
        if name:
            return os.path.join(data_dir.get_tmp_dir(),
                                "serial-%s-%s" % (name, self.instance))
        return os.path.join(data_dir.get_tmp_dir(),
                            "serial-%s" % self.instance)

    def get_serial_console_filenames(self):
        """
        Return a list of all serial console filenames
        (as specified in the VM's params).
        """
        return [self.get_serial_console_filename(_) for _ in
                self.params.objects("serials")]

    def cleanup_serial_console(self):
        """
        Close serial console and associated log file
        """
        for console_type in ["virtio_console", "serial_console"]:
            if hasattr(self, console_type):
                console = getattr(self, console_type)
                if console:
                    console.close()
                    console = None
        if hasattr(self, "migration_file"):
            try:
                os.unlink(self.migration_file)
            except OSError:
                pass

    def make_create_command(self, name=None, params=None, root_dir=None):
        """
        Generate a qemu command line. All parameters are optional. If a
        parameter is not supplied, the corresponding value stored in the
        class attributes is used.

        :param name: The name of the object
        :param params: A dict containing VM params
        :param root_dir: Base directory for relative filenames

        :note: The params dict should contain:
               mem -- memory size in MBs
               cdrom -- ISO filename to use with the qemu -cdrom parameter
               extra_params -- a string to append to the qemu command
               shell_port -- port of the remote shell daemon on the guest
               (SSH, Telnet or the home-made Remote Shell Server)
               shell_client -- client program to use for connecting to the
               remote shell daemon on the guest (ssh, telnet or nc)
               x11_display -- if specified, the DISPLAY environment variable
               will be be set to this value for the qemu process (useful for
               SDL rendering)
               images -- a list of image object names, separated by spaces
               nics -- a list of NIC object names, separated by spaces

               For each image in images:
               drive_format -- string to pass as 'if' parameter for this
               image (e.g. ide, scsi)
               image_snapshot -- if yes, pass 'snapshot=on' to qemu for
               this image
               image_boot -- if yes, pass 'boot=on' to qemu for this image
               In addition, all parameters required by get_image_filename.

               For each NIC in nics:
               nic_model -- string to pass as 'model' parameter for this
               NIC (e.g. e1000)
        """
        # Helper function for command line option wrappers
        def _add_option(option, value, option_type=None, first=False):
            """
            Add option to qemu parameters.
            """
            if first:
                fmt = " %s=%s"
            else:
                fmt = ",%s=%s"
            if option_type is bool:
                # Decode value for bool parameter (supports True, False, None)
                if value in ['yes', 'on', True]:
                    return fmt % (option, "on")
                elif value in ['no', 'off', False]:
                    return fmt % (option, "off")
            elif value and isinstance(value, bool):
                return fmt % (option, "on")
            elif value and isinstance(value, six.string_types):
                # "EMPTY_STRING" and "NULL_STRING" is used for testing illegal
                # foramt of option.
                # "EMPTY_STRING": set option as a empty string "".
                # "NO_EQUAL_STRING": set option as a option string only,
                #                    even without "=".
                #      (In most case, qemu-kvm should recognize it as "<null>")
                if value == "NO_EQUAL_STRING":
                    return ",%s" % option
                if value == "EMPTY_STRING":
                    value = '""'
                return fmt % (option, str(value))
            return ""

        # Wrappers for all supported qemu command line parameters.
        # This is meant to allow support for multiple qemu versions.
        # Each of these functions receives the output of 'qemu -help'
        # as a parameter, and should add the requested command line
        # option accordingly.
        def add_name(name):
            return " -name '%s'" % name

        def process_sandbox(devices, action):
            if action == "add":
                if devices.has_option("sandbox"):
                    return " -sandbox on "
            elif action == "rem":
                if devices.has_option("sandbox"):
                    return " -sandbox off "

        def add_human_monitor(devices, monitor_name, filename):
            if not devices.has_option("chardev"):
                return " -monitor unix:'%s',server,nowait" % filename

            monitor_id = "hmp_id_%s" % monitor_name
            chardev_params = params.object_params(monitor_name)
            # only support default chardev_backend 'unix_socket' for hmp monitor
            backend = chardev_params.get('chardev_backend', 'unix_socket')
            if backend != 'unix_socket':
                raise NotImplementedError("human monitor don't support backend"
                                          " %s" % backend)
            params["monitor_filename_%s" % monitor_name] = filename
            char_device = devices.chardev_define_by_params(
                monitor_id, chardev_params, filename)
            devices.insert(char_device)
            cmd = " -mon chardev=%s" % monitor_id
            cmd += _add_option("mode", "readline")
            return cmd

        def add_qmp_monitor(devices, monitor_name, filename):
            if not devices.has_option("qmp"):
                LOG.warn("Fallback to human monitor since qmp is"
                         " unsupported")
                return add_human_monitor(devices, monitor_name, filename)

            if not devices.has_option("chardev"):
                return " -qmp unix:'%s',server,nowait" % filename

            chardev_params = params.object_params(monitor_name)
            backend = chardev_params.get('chardev_backend', 'unix_socket')
            monitor_id = "qmp_id_%s" % monitor_name
            if backend == 'tcp_socket':
                host = chardev_params.get('chardev_host', '127.0.0.1')
                port = str(utils_misc.find_free_ports(5000, 6000, 1, host)[0])
                chardev_params['chardev_host'] = host
                chardev_params['chardev_port'] = port
                params["chardev_host_%s" % monitor_name] = host
                params["chardev_port_%s" % monitor_name] = port
            elif backend == 'unix_socket':
                params["monitor_filename_%s" % monitor_name] = filename
            char_device = devices.chardev_define_by_params(
                monitor_id, chardev_params, filename)
            devices.insert(char_device)

            cmd = " -mon chardev=%s" % monitor_id
            cmd += _add_option("mode", "control")
            return cmd

        def add_log_seabios(devices):
            if not devices.has_device("isa-debugcon"):
                return ""

            default_id = "seabioslog_id_%s" % self.instance
            filename = os.path.join(data_dir.get_tmp_dir(),
                                    "seabios-%s" % self.instance)
            self.logs["seabios"] = filename
            cmd = " -chardev socket"
            cmd += _add_option("id", default_id)
            cmd += _add_option("path", filename)
            cmd += _add_option("server", "on")
            cmd += _add_option("wait", "off")
            cmd += " -device isa-debugcon"
            cmd += _add_option("chardev", default_id)
            cmd += _add_option("iobase", "0x402")
            return cmd

        def add_log_anaconda(devices, pci_bus='pci.0'):
            chardev_id = "anacondalog_chardev_%s" % self.instance
            vioser_id = "anacondalog_vioser_%s" % self.instance
            filename = os.path.join(data_dir.get_tmp_dir(),
                                    "anaconda-%s" % self.instance)
            self.logs["anaconda"] = filename
            dev = qdevices.QCustomDevice('chardev', backend='backend')
            dev.set_param('backend', 'socket')
            dev.set_param('id', chardev_id)
            dev.set_param("path", filename)
            dev.set_param("server", 'on')
            dev.set_param("wait", 'off')
            devices.insert(dev)
            if '-mmio:' in params.get('machine_type'):
                dev = QDevice('virtio-serial-device')
            elif params.get('machine_type').startswith("s390"):
                dev = QDevice("virtio-serial-ccw")
            else:
                dev = QDevice('virtio-serial-pci', parent_bus=pci_bus)
            dev.set_param("id", vioser_id)
            devices.insert(dev)
            dev = QDevice('virtserialport')
            dev.set_param("bus", "%s.0" % vioser_id)
            dev.set_param("chardev", chardev_id)
            dev.set_param("name", "org.fedoraproject.anaconda.log.0")
            devices.insert(dev)

        def add_smp(devices):
            smp_str = " -smp %d" % self.cpuinfo.smp
            smp_pattern = "smp .*\[,maxcpus=.*\].*"
            if devices.has_option(smp_pattern):
                smp_str += ",maxcpus=%d" % self.cpuinfo.maxcpus
            if self.cpuinfo.cores != 0:
                smp_str += ",cores=%d" % self.cpuinfo.cores
            if self.cpuinfo.threads != 0:
                smp_str += ",threads=%d" % self.cpuinfo.threads
            if self.cpuinfo.dies != 0:
                smp_str += ",dies=%d" % self.cpuinfo.dies
            if self.cpuinfo.sockets != 0:
                smp_str += ",sockets=%d" % self.cpuinfo.sockets
            return smp_str

        def add_nic(devices, vlan, model=None, mac=None, device_id=None,
                    netdev_id=None, nic_extra_params=None, pci_addr=None,
                    bootindex=None, queues=1, vectors=None, pci_bus='pci.0',
                    ctrl_mac_addr=None, mq=None, failover=None):
            if model == 'none':
                return
            if devices.has_option("device"):
                if not model:
                    model = "rtl8139"
                elif model == "virtio":
                    machine_type = self.params.get("machine_type")
                    if "s390" in machine_type:
                        model = "virtio-net-ccw"
                    elif '-mmio:' in machine_type:
                        model = "virtio-net-device"
                    else:
                        model = "virtio-net-pci"
                dev = QDevice(model)
                if ctrl_mac_addr and ctrl_mac_addr in ["on", "off"]:
                    dev.set_param('ctrl_mac_addr', ctrl_mac_addr)
                dev.set_param('mac', mac, dynamic=True)
                # only pci domain=0,bus=0,function=0 is supported for now.
                #
                # libvirt gains the pci_slot, free_pci_addr here,
                # value by parsing the xml file, i.e. counting all the
                # pci devices and store the number.
                if model == 'virtio-net-device':
                    dev.parent_bus = {'type': 'virtio-bus'}
                elif model == 'virtio-net-ccw':  # For s390x platform
                    dev.parent_bus = {'type': 'virtio-bus'}
                elif model != 'spapr-vlan':
                    dev.parent_bus = pci_bus
                    dev.set_param('addr', pci_addr)
                if nic_extra_params:
                    nic_extra_params = (_.split('=', 1) for _ in
                                        nic_extra_params.split(',') if _)
                    for key, val in nic_extra_params:
                        dev.set_param(key, val)
                dev.set_param("bootindex", bootindex)
                if 'aarch64' in params.get('vm_arch_name', arch.ARCH):
                    if "rombar" in devices.execute_qemu("-device %s,?"
                                                        % model):
                        dev.set_param("rombar", 0)
            else:
                dev = qdevices.QCustomDevice('net', backend='type')
                dev.set_param('type', 'nic')
                dev.set_param('model', model)
                dev.set_param('macaddr', mac, 'NEED_QUOTE', True)
            dev.set_param('id', device_id, 'NEED_QUOTE')
            if "virtio" in model:
                if int(queues) > 1:
                    mq = 'on' if mq is None else mq
                    dev.set_param('mq', mq)
                if vectors:
                    dev.set_param('vectors', vectors)
                if failover:
                    dev.set_param('failover', failover)
            if devices.has_option("netdev"):
                dev.set_param('netdev', netdev_id)
            else:
                dev.set_param('vlan', vlan)
            devices.insert(dev)

        def add_net(devices, vlan, nettype, ifname=None, tftp=None,
                    bootfile=None, hostfwd=[], netdev_id=None,
                    netdev_extra_params=None, tapfds=None, script=None,
                    downscript=None, vhost=None, queues=None, vhostfds=None,
                    add_queues=None, helper=None, add_tapfd=None,
                    add_vhostfd=None, vhostforce=None):
            mode = None
            if nettype in ['bridge', 'network', 'macvtap']:
                mode = 'tap'
            elif nettype == 'user':
                mode = 'user'
            else:
                LOG.warning("Unknown/unsupported nettype %s" % nettype)
                return ''

            if devices.has_option("netdev"):
                cmd = " -netdev %s,id=%s" % (mode, netdev_id)
                cmd_nd = cmd
                if vhost:
                    if vhost in ["on", "off"]:
                        cmd += ",vhost=%s" % vhost
                    elif vhost == "vhost=on":  # Keeps compatibility with old.
                        cmd += ",%s" % vhost
                    cmd_nd = cmd
                    if vhostfds:
                        if (int(queues) > 1 and
                                'vhostfds=' in devices.get_help_text()):
                            cmd += ",vhostfds=%(vhostfds)s"
                            cmd_nd += ",vhostfds=DYN"
                        else:
                            txt = ""
                            if int(queues) > 1:
                                txt = "qemu do not support vhost multiqueue,"
                                txt += " Fall back to single queue."
                            if 'vhostfd=' in devices.get_help_text():
                                cmd += ",vhostfd=%(vhostfd)s"
                                cmd_nd += ",vhostfd=DYN"
                            else:
                                txt += " qemu do not support vhostfd."
                            if txt:
                                LOG.warn(txt)
                        # For negative test
                        if add_vhostfd:
                            cmd += ",vhostfd=%(vhostfd)s"
                            cmd_nd += ",vhostfd=%(vhostfd)s"
                if vhostforce in ["on", "off"]:
                    cmd += ",vhostforce=%s" % vhostforce
                    cmd_nd = cmd
                if netdev_extra_params:
                    cmd += "%s" % netdev_extra_params
                    cmd_nd += "%s" % netdev_extra_params
            else:
                cmd = " -net %s,vlan=%d" % (mode, vlan)
                cmd_nd = cmd
            if mode == "tap":
                if script:
                    cmd += ",script='%s'" % script
                    cmd += ",downscript='%s'" % (downscript or "no")
                    cmd_nd = cmd
                    if ifname:
                        cmd += ",ifname='%s'" % ifname
                        cmd_nd = cmd
                elif tapfds:
                    if (int(queues) > 1 and
                            ',fds=' in devices.get_help_text()):
                        cmd += ",fds=%(tapfds)s"
                        cmd_nd += ",fds=DYN"
                    else:
                        cmd += ",fd=%(tapfd)s"
                        cmd_nd += ",fd=DYN"
                    # For negative test
                    if add_tapfd:
                        cmd += ",fd=%(tapfd)s"
                        cmd_nd += ",fd=%(tapfd)s"
            elif mode == "user":
                if tftp and "[,tftp=" in devices.get_help_text():
                    cmd += ",tftp='%s'" % tftp
                    cmd_nd = cmd
                if bootfile and "[,bootfile=" in devices.get_help_text():
                    cmd += ",bootfile='%s'" % bootfile
                    cmd_nd = cmd
                if "[,hostfwd=" in devices.get_help_text():
                    for i in xrange(len(hostfwd)):
                        cmd += (",hostfwd=tcp::%%(host_port%d)s"
                                "-:%%(guest_port%d)s" % (i, i))
                        cmd_nd += ",hostfwd=tcp::DYN-:%%(guest_port)ds"

            if add_queues and queues:
                cmd += ",queues=%s" % queues
                cmd_nd += ",queues=%s" % queues

            if helper:
                cmd += ",helper=%s" % helper
                cmd_nd += ",helper=%s" % helper

            return cmd, cmd_nd

        def add_floppy(devices, params):
            # We may want to add {floppy_otps} parameter for -fda, -fdb
            # {fat:floppy:}/path/. However vvfat is not usually recommended.
            devs = []
            for floppy_name in params.objects('floppies'):
                image_params = params.object_params(floppy_name)
                # TODO: Unify image, cdrom, floppy params
                image_params['drive_format'] = 'floppy'
                image_params[
                    'image_readonly'] = image_params.get("floppy_readonly",
                                                         "no")
                # Use the absolute patch with floppies (pure *.vfd)
                image_params['image_raw_device'] = 'yes'
                image_params['image_name'] = utils_misc.get_path(
                    data_dir.get_data_dir(),
                    image_params["floppy_name"])
                image_params['image_format'] = None
                devs += devices.images_define_by_params(floppy_name,
                                                        image_params,
                                                        media='')
            # q35 machine has the different cmdline for floppy devices,
            # and not like other types of storage, all the drives would
            # attach to the same one floppy device, so have to do some
            # workaround here
            if 'q35' in params['machine_type']:
                devs = [dev for dev in devs
                        if isinstance(dev, qdevices.QDrive)]
                if devs:
                    floppy = QDevice('isa-fdc')
                    for index, drive in enumerate(devs):
                        drive_key = 'drive%s' % chr(index + 65)
                        floppy.set_param(drive_key, drive['id'])
                    devs.append(floppy)
            devices.insert(devs)

        def add_tftp(devices, filename):
            # If the new syntax is supported, don't add -tftp
            if "[,tftp=" in devices.get_help_text():
                return ""
            else:
                return " -tftp '%s'" % filename

        def add_bootp(devices, filename):
            # If the new syntax is supported, don't add -bootp
            if "[,bootfile=" in devices.get_help_text():
                return ""
            else:
                return " -bootp '%s'" % filename

        def add_tcp_redir(devices, host_port, guest_port):
            # If the new syntax is supported, don't add -redir
            if "[,hostfwd=" in devices.get_help_text():
                return ""
            else:
                return " -redir tcp:%s::%s" % (host_port, guest_port)

        def add_vnc(vnc_port, vnc_password='no', extra_params=None):
            vnc_cmd = " -vnc :%d" % (vnc_port - 5900)
            if vnc_password == "yes":
                vnc_cmd += ",password"
            if extra_params:
                vnc_cmd += ",%s" % extra_params
            return vnc_cmd

        def add_sdl(devices):
            if devices.has_option("sdl"):
                return " -sdl"
            else:
                return ""

        def add_nographic():
            return " -nographic"

        def add_uuid(uuid):
            return " -uuid '%s'" % uuid

        def add_qemu_option(devices, name, optsinfo):
            """
            Add qemu option, such as '-msg timestamp=on|off'

            :param devices: qcontainer object
            :param name: string type option name
            :param optsinfo: list like [(key, val, vtype)]
            """
            if devices.has_option(name):
                options = []
                for info in optsinfo:
                    key, val = info[:2]
                    if key and val:
                        options.append("%s=%%(%s)s" % (key, key))
                    else:
                        options += list(filter(None, info[:2]))
                options = ",".join(options)
                cmdline = "-%s %s" % (name, options)
                device = qdevices.QStringDevice(name, cmdline=cmdline)
                for info in optsinfo:
                    key, val, vtype = info
                    if key and val:
                        device.set_param(key, val, vtype, False)
                devices.insert(device)
            else:
                LOG.warn("option '-%s' not supportted" % name)

        def add_pcidevice(devices, host, params, device_driver="pci-assign",
                          pci_bus='pci.0'):
            if devices.has_device(device_driver):
                dev = QDevice(device_driver, parent_bus=pci_bus)
            else:
                dev = qdevices.QCustomDevice('pcidevice', parent_bus=pci_bus)
            help_cmd = "%s -device %s,\? 2>&1" % (qemu_binary, device_driver)
            pcidevice_help = process.run(help_cmd, shell=True,
                                         verbose=False).stdout_text
            dev.set_param('host', host)
            dev.set_param('id', 'id_%s' % host.replace(":", "."))
            dev.set_param('failover_pair_id', failover_pair_id)
            fail_param = []
            for param in params.get("pci-assign_params", "").split():
                value = params.get(param)
                if value:
                    if param in pcidevice_help:
                        dev.set_param(param, value)
                    else:
                        fail_param.append(param)
            if fail_param:
                msg = ("parameter %s is not support in device pci-assign."
                       " It only support following parameter:\n %s" %
                       (", ".join(fail_param), pcidevice_help))
                LOG.warn(msg)
            devices.insert(dev)

        def add_virtio_rng(devices, rng_params, parent_bus="pci.0"):
            """
            Add virtio-rng device.

            :param devices: qcontainer object to contain devices.
            :param rng_params: dict include virtio_rng device params.
            :param parent_bus: parent bus for virtio-rng-pci.
            """
            def set_dev_params(dev, dev_params,
                               dev_backend, backend_type):
                """
                Set QCustomDevice properties by user params dict.
                """
                for pro, val in six.iteritems(dev_params):
                    suffix = "_%s" % backend_type
                    if pro.endswith(suffix):
                        idx = len(suffix)
                        dev.set_param(pro[:-idx], val)
                if dev_backend:
                    dev.set_param("backend", dev_backend)
                dev_id = utils_misc.generate_random_string(8)
                dev_id = "%s-%s" % (backend_type, dev_id)
                dev.set_param("id", dev_id)

            dev_type = "virtio-rng-pci"
            machine_type = self.params.get("machine_type", "pc")
            if "s390" in machine_type:
                dev_type = "virtio-rng-ccw"
                parent_bus = None
            if devices.has_device(dev_type):
                rng_pci = QDevice(dev_type, parent_bus=parent_bus)
                set_dev_params(rng_pci, rng_params, None, dev_type)

                rng_dev = qdevices.QCustomDevice(dev_type="object",
                                                 backend="backend")
                backend = rng_params["backend"]
                backend_type = rng_params["backend_type"]
                set_dev_params(rng_dev, rng_params, backend, backend_type)

                if backend_type == "chardev":
                    backend = rng_params["rng_chardev_backend"]
                    backend_type = rng_params["%s_type" % backend]
                    char_dev = qdevices.QCustomDevice(dev_type="chardev",
                                                      backend="backend")
                    set_dev_params(char_dev, rng_params,
                                   backend, backend_type)
                    rng_dev.set_param("chardev", char_dev.get_qid())
                    devices.insert(char_dev)
                devices.insert(rng_dev)
                rng_pci.set_param("rng", rng_dev.get_qid())
                devices.insert(rng_pci)

        def add_memorys(devices, params):
            """
            Add memory controller by params.

            :param devices: VM devices container
            """
            options, devs = [], []
            normalize_data_size = utils_misc.normalize_data_size
            mem = params.get("mem", None)
            mem_params = params.object_params("mem")
            # if params["mem"] is provided, use the value provided
            if mem:
                mem_size_m = "%sM" % mem_params["mem"]
                mem_size_m = float(normalize_data_size(mem_size_m))
            # if not provided, use automem
            else:
                usable_mem_m = utils_misc.get_usable_memory_size(align=512)
                if not usable_mem_m:
                    raise exceptions.TestError("Insufficient memory to"
                                               " start a VM.")
                LOG.info("Auto set guest memory size to %s MB" %
                         usable_mem_m)
                mem_size_m = usable_mem_m

            # vm_mem_limit(max) and vm_mem_minimum(min) take control here
            if mem_params.get("vm_mem_limit"):
                max_mem_size_m = params.get("vm_mem_limit")
                max_mem_size_m = float(normalize_data_size(max_mem_size_m))
                if mem_size_m >= max_mem_size_m:
                    LOG.info("Guest max memory is limited to %s"
                             % max_mem_size_m)
                    mem_size_m = max_mem_size_m

            if mem_params.get("vm_mem_minimum"):
                min_mem_size_m = params.get("vm_mem_minimum")
                min_mem_size_m = float(normalize_data_size(min_mem_size_m))
                if mem_size_m < min_mem_size_m:
                    raise exceptions.TestCancel("Guest min memory has to be %s"
                                                ", got %s" % (min_mem_size_m,
                                                              mem_size_m))

            params["mem"] = str(int(mem_size_m))
            options.append(params["mem"])
            if devices.has_device("pc-dimm"):
                if mem_params.get("maxmem"):
                    options.append("maxmem=%s" % mem_params["maxmem"])
                    if mem_params.get("slots"):
                        options.append("slots=%s" % mem_params["slots"])
                for name in params.objects("mem_devs"):
                    dev = devices.memory_define_by_params(params, name)
                    devs.extend(dev)
            machine_dev = devices.get_by_properties({"type": "machine"})[0]
            machine_cmd = machine_dev.cmdline_nd()
            output = re.findall(r",memory-backend=mem-([\w|-]+)", machine_cmd)
            if output:
                name = output[0]
                backend_options = {}
                backend_options["size_mem"] = "%sM" % params["mem"]
                if params.get("hugepage_path"):
                    backend_options["backend_mem"] = "memory-backend-file"
                    backend_options["mem-path_mem"] = params["hugepage_path"]
                backend_options["share_mem"] = params.get("vm_mem_share")
                backend_param = Params(backend_options)
                dev = devices.memory_object_define_by_params(backend_param,
                                                             name)
                devs.append(dev)
            else:
                if params.get("hugepage_path") \
                        and not params.get("guest_numa_nodes"):
                    cmd = "-mem-path %s" % params["hugepage_path"]
                    devs.append(StrDev('mem-path', cmdline=cmd))

            cmdline = "-m %s" % ",".join(map(str, options))
            devs.insert(0, StrDev("mem", cmdline=cmdline))
            devices.insert(devs)
            return devices

        def add_spice(spice_options, port_range=(3000, 3199),
                      tls_port_range=(3200, 3399)):
            """
            processes spice parameters
            :param spice_options - dict with spice keys/values
            :param port_range - tuple with port range, default: (3000, 3199)
            :param tls_port_range - tuple with tls port range,
                                    default: (3200, 3399)
            """
            spice_opts = []  # will be used for ",".join()
            tmp = None

            def optget(opt):
                """a helper function"""
                return spice_options.get(opt)

            def set_yes_no_value(key, yes_value=None, no_value=None):
                """just a helper function"""
                tmp = optget(key)
                if tmp == "no" and no_value:
                    spice_opts.append(no_value)

                elif tmp == "yes" and yes_value:
                    spice_opts.append(yes_value)

            def set_value(opt_string, key, fallback=None):
                """just a helper function"""
                tmp = optget(key)
                if tmp:
                    spice_opts.append(opt_string % tmp)
                elif fallback:
                    spice_opts.append(fallback)
            if optget("spice_port") == "generate":
                # FIXME: This makes the "needs_restart" to always re-create the
                # machine.
                s_port = str(utils_misc.find_free_port(*port_range))
                spice_options['spice_port'] = s_port
                spice_opts.append("port=%s" % s_port)
            # spice_port = no: spice_port value is not present on qemu cmdline
            elif optget("spice_port") != "no":
                set_value("port=%s", "spice_port")

            password = optget("spice_password")
            secret_cmdline = ''
            if password:
                if ("password-secret" not in
                        devices.execute_qemu("-spice help")):
                    spice_opts.append('password=%s' % password)
                else:
                    secret_id = 'spice_sec0'
                    secret_cmdline = devices.secret_object_define_by_varibles(
                        secret_id, data=password).cmdline()
                    spice_opts.append('password-secret=%s' % secret_id)
            else:
                spice_opts.append("disable-ticketing=on")
            ip_ver = optget("listening_addr")
            if ip_ver:
                host_ip = utils_net.get_host_ip_address(self.params, ip_ver)
                spice_options['spice_addr'] = host_ip
            set_yes_no_value("disable_copy_paste",
                             yes_value="disable-copy-paste=on",
                             no_value="disable-copy-paste=off")
            set_value("addr=%s", "spice_addr")

            if optget("spice_ssl") == "yes":
                # SSL only part
                if optget("spice_tls_port") == "generate":
                    t_port = str(utils_misc.find_free_port(*tls_port_range))
                    spice_options['spice_tls_port'] = t_port
                    spice_opts.append("tls-port=%s" % t_port)
                # spice_tls_port = no: spice_port value is not present on qemu
                # cmdline
                elif optget("spice_tls_port") != "no":
                    set_value("tls-port=%s", "spice_tls_port")

                prefix = optget("spice_x509_prefix")
                if ((prefix is None or not os.path.exists(prefix)) and
                        (optget("spice_gen_x509") == "yes")):
                    # Generate spice_x509_* is not always necessary,
                    # Regenerate them will make your existing VM
                    # not longer accessible via encrypted spice.
                    c_subj = optget("spice_x509_cacert_subj")
                    s_subj = optget("spice_x509_server_subj")
                    # If CN is not specified, add IP of host
                    if s_subj[-3:] == "CN=":
                        s_subj += utils_net.get_host_ip_address(self.params)
                    passwd = optget("spice_x509_key_password")
                    secure = optget("spice_x509_secure")

                    utils_misc.create_x509_dir(prefix, c_subj, s_subj, passwd,
                                               secure)

                tmp = optget("spice_x509_dir")
                if tmp == "yes":
                    spice_opts.append("x509-dir=%s" % (prefix))

                elif tmp == "no":
                    cacert = optget("spice_x509_cacert_file")
                    server_key = optget("spice_x509_key_file")
                    server_cert = optget("spice_x509_cert_file")
                    keyfile_str = ("x509-key-file=%s,x509-cacert-file=%s,"
                                   "x509-cert-file=%s" %
                                   (os.path.join(prefix, server_key),
                                    os.path.join(prefix, cacert),
                                    os.path.join(prefix, server_cert)))
                    spice_opts.append(keyfile_str)

                set_yes_no_value("spice_x509_secure",
                                 yes_value="x509-key-password=%s" %
                                 (optget("spice_x509_key_password")))

                tmp = optget("spice_secure_channels")
                if tmp:
                    for item in tmp.split(","):
                        spice_opts.append("tls-channel=%s" % (item.strip()))

                tmp = optget("spice_plaintext_channels")
                if tmp:
                    for item in tmp.split(","):
                        spice_opts.append("plaintext-channel=%s" % (item.strip()))

            # Less common options
            set_value("seamless-migration=%s", "spice_seamless_migration")
            set_value("image-compression=%s", "spice_image_compression")
            set_value("jpeg-wan-compression=%s", "spice_jpeg_wan_compression")
            set_value("zlib-glz-wan-compression=%s",
                      "spice_zlib_glz_wan_compression")
            set_value("streaming-video=%s", "spice_streaming_video")
            set_value("agent-mouse=%s", "spice_agent_mouse")
            set_value("playback-compression=%s", "spice_playback_compression")

            set_yes_no_value("spice_ipv4",
                             yes_value="ipv4=on", no_value="ipv4=off")
            set_yes_no_value("spice_ipv6",
                             yes_value="ipv6=on", no_value="ipv6=off")

            return secret_cmdline + " -spice %s" % (",".join(spice_opts))

        def add_qxl(qxl_nr, base_addr=29):
            """
            adds extra qxl devices

            :param qxl_nr total number of qxl devices
            :param base_addr: base address of extra qxl device
            """
            qxl_str = ""
            for index in range(1, qxl_nr):
                addr = base_addr + index
                qxl_str += " -device qxl,id=video%d,addr=0x%x" % (index, addr)
            return qxl_str

        def add_vga(devices, vga):
            """Add primary vga device."""
            fallback = params.get("vga_use_legacy_expression") == "yes"
            machine_type = params.get("machine_type", '')
            parent_bus = {'aobject': 'pci.0'}
            vga_dev_map = {
                "std": "VGA",
                "cirrus": "cirrus-vga",
                "vmware": "vmware-svga",
                "qxl": "qxl-vga",
                "virtio": "virtio-vga"
            }
            vga_dev = vga_dev_map.get(vga, None)
            if machine_type.startswith('arm64-pci:'):
                if vga == 'virtio' and not devices.has_device(vga_dev):
                    # Arm doesn't usually supports 'virtio-vga'
                    vga_dev = 'virtio-gpu-pci'
            elif machine_type.startswith('s390-ccw-virtio'):
                if vga == 'virtio':
                    vga_dev = 'virtio-gpu-ccw'
                    parent_bus = None
                else:
                    vga_dev = None
            elif '-mmio:' in machine_type:
                if vga == 'virtio':
                    vga_dev = 'virtio-gpu-device'
                    parent_bus = None
                else:
                    vga_dev = None
            if vga_dev is None:
                fallback = True
                parent_bus = None
            # fallback if qemu not has such a device
            elif not devices.has_device(vga_dev):
                fallback = True
            if fallback:
                name = "VGA-%s" % vga
                cmdline = " -vga %s" % vga
                return StrDev(name, cmdline=cmdline, parent_bus=parent_bus)
            return QDevice(vga_dev, parent_bus=parent_bus)

        def add_kernel(filename):
            return " -kernel '%s'" % filename

        def add_initrd(filename):
            return " -initrd '%s'" % filename

        def add_rtc(devices):
            # Pay attention that rtc-td-hack is for early version
            # if "rtc " in help:
            if devices.has_option("rtc"):
                cmd = _add_option("base", params.get("rtc_base"))
                cmd += _add_option("clock", params.get("rtc_clock"))
                cmd += _add_option("driftfix", params.get("rtc_drift"))
                if cmd:
                    return " -rtc %s" % cmd.lstrip(",")
            elif devices.has_option("rtc-td-hack"):
                return " -rtc-td-hack"
            return ""

        def add_kernel_cmdline(cmdline):
            return " -append '%s'" % cmdline

        def add_testdev(devices, filename=None):
            if devices.has_device("testdev"):
                return (" -chardev file,id=testlog,path=%s"
                        " -device testdev,chardev=testlog" % filename)
            elif devices.has_device("pc-testdev"):
                return " -device pc-testdev"
            else:
                return ""

        def add_isa_debug_exit(devices, iobase=0xf4, iosize=0x04):
            if devices.has_device("isa-debug-exit"):
                return (" -device isa-debug-exit,iobase=%s,iosize=%s" %
                        (iobase, iosize))
            else:
                return ""

        def add_no_hpet(devices):
            if devices.has_option("no-hpet"):
                return " -no-hpet"
            else:
                return ""

        def add_cpu_flags(devices, cpu_model, flags=None, vendor_id=None,
                          family=None):
            if not devices.has_option('cpu'):
                return ""

            cmd = " -cpu '%s'" % cpu_model
            if vendor_id:
                cmd += ",vendor=\"%s\"" % vendor_id
            if flags:
                if not flags.startswith(","):
                    cmd += ","
                cmd += "%s" % flags
            # CPU flag 'erms' is required by Win10 and Win2016 guest, if VM's
            # CPU model is 'Penryn' or 'Nehalem'(see detail RHBZ#1252134), and
            # it's harmless for other guest, so add it here.
            if cpu_model in ['Penryn', 'Nehalem']:
                recognize_flags = cpu.get_recognized_cpuid_flags(qemu_binary)
                if not ('erms' in flags or 'erms' in recognize_flags):
                    cmd += ',+erms'
            if family:
                cmd += ",family=%s" % family
            return cmd

        def add_boot(devices, opts):
            machine_type = params.get('machine_type', "")
            if (machine_type.startswith("arm") or
                    machine_type.startswith('riscv')):
                LOG.warn("-boot on %s is usually not supported, use "
                         "bootindex instead.", machine_type)
                return ""
            if machine_type.startswith("s390"):
                LOG.warn("-boot on s390x only support boot strict=on")
                return "-boot strict=on"
            cmd = " -boot"
            options = []
            for p in list(opts.keys()):
                pattern = "boot .*?(\[,?%s=(.*?)\]|\s+)" % p
                if devices.has_option(pattern):
                    option = opts[p]
                    if option is not None:
                        options.append("%s=%s" % (p, option))
            if devices.has_option("boot \[a\|c\|d\|n\]"):
                cmd += " %s" % opts["once"]
            elif options:
                cmd += " %s" % ",".join(options)
            else:
                cmd = ""
            return cmd

        def get_index(index):
            while self.index_in_use.get(str(index)):
                index += 1
            return index

        def add_sga(devices):
            if not devices.has_device("sga"):
                return ""
            else:
                return " -device sga"

        def add_watchdog(devices, device_type=None, action="reset"):
            watchdog_devs = []
            parent_bus = None
            if device_type and devices.has_device(device_type):
                if devices.is_pci_device(device_type):
                    parent_bus = self._get_pci_bus(self.params, None, False)
                watchdog_devs.append(QDevice(device_type, parent_bus=parent_bus))
            cmd = "-watchdog-action %s" % action
            watchdog_devs.append(StrDev('watchdog_action', cmdline=cmd))
            return watchdog_devs

        def add_option_rom(devices, opt_rom):
            if not devices.has_option("option-rom"):
                return ""

            return " -option-rom %s" % opt_rom

        def add_smartcard(sc_chardev, sc_id):
            sc_cmd = " -device usb-ccid,id=ccid0"
            sc_cmd += " -chardev " + sc_chardev
            sc_cmd += ",id=" + sc_id + ",name=smartcard"
            sc_cmd += " -device ccid-card-passthru,chardev=" + sc_id

            return sc_cmd

        def add_numa_node(devices, memdev=None, mem=None,
                          cpus=None, nodeid=None, initiator=None):
            """
            This function is used to add numa node to guest command line
            """
            if not devices.has_option("numa"):
                return ""
            numa_cmd = " -numa node"
            if mem is not None:
                numa_cmd += ",mem=%s" % mem
            elif memdev is not None:
                numa_cmd += ",memdev=%s" % memdev
            if cpus is not None:
                cpus = map(lambda x: x.strip(), cpus.split(','))
                cpus = ','.join(map(lambda x: "cpus=%s" % x, cpus))
                numa_cmd += ",%s" % cpus
            if nodeid is not None:
                numa_cmd += ",nodeid=%s" % nodeid
            if initiator is not None:
                numa_cmd += ",initiator=%s" % initiator
            return numa_cmd

        def add_numa_cpu(devices, node_id, socket_id=None, die_id=None,
                         core_id=None, thread_id=None):
            """
            This function is used to add numa cpu to guest command line
            node-id=node[,socket-id=x][,die-id=y],[core-id=y][,thread-id=z]
            """
            if not devices.has_option("numa cpu,.*"):
                return ""
            numa_cpu_cmd = " -numa cpu,node-id=%s" % node_id
            options = {"socket-id": socket_id, "die-id": die_id,
                       "core-id": core_id, "thread-id": thread_id}
            for key, value in options.items():
                if value is not None:
                    numa_cpu_cmd += ",%s=%s" % (key, value)
            return numa_cpu_cmd

        def add_balloon(devices, devid=None, bus=None,
                        use_old_format=None, options={}):
            """
            This function is used to add balloon device

            :param devices: device container object
            :param devid: device id
            :param bus: the bus balloon device use
            :param use_old_format: use old format or not
            :param options: optional keyword arguments
            """
            if not devices.has_option("device") or use_old_format is True:
                devices.insert(StrDev('balloon', cmdline=" -balloon virtio"))
                return
            machine_type = self.params.get("machine_type")
            if "s390" in machine_type:    # For s390x platform
                model = "virtio-balloon-ccw"
                bus = {'type': 'virtio-bus'}
            else:
                model = "virtio-balloon-pci"
            dev = QDevice(model, parent_bus=bus)
            if devid:
                dev.set_param("id", devid)
            for key, value in options.items():
                dev.set_param(key, value)
            devices.insert(dev)

        def add_pci_controllers(devices, params):
            """
            Insert pci controllers into qcontainer by order.

            :param devices: qcontainer object
            :param params: test params
            """
            def sort_key(dev):
                """
                Function used to sort pcic list
                """
                order_pcics = ['pcie-root-port', 'ioh3420', 'x3130-upstream',
                               'x3130', 'i82801b11-bridge',
                               'pci-bridge']
                try:
                    return order_pcics.index(dev.get_param('driver'))
                except ValueError:
                    return -1

            pcics = []
            for pcic in params.objects("pci_controllers"):
                dev = devices.pcic_by_params(pcic, params.object_params(pcic))
                pcics.append(dev)
            if params.get("pci_controllers_autosort", "yes") == "yes":
                pcics.sort(key=sort_key, reverse=False)
            devices.insert(pcics)
        # End of command line option wrappers

        # If nothing changed and devices exists, return immediately
        if (name is None and params is None and root_dir is None and
                self.devices is not None):
            return self.devices, self.spice_options

        if name is None:
            name = self.name
        if params is None:
            params = self.params
        if root_dir is None:
            root_dir = self.root_dir

        pci_bus = {'aobject': params.get('pci_bus', 'pci.0')}
        spice_options = {}

        # init value by default.
        # PCI addr 0,1,2 are taken by PCI/ISA/IDE bridge and the GPU.
        self.pci_addr_list = [0, 1, 2]

        # Clone this VM using the new params
        vm = self.clone(name, params, root_dir, copy_state=True)

        self.last_boot_index = 0
        if params.get("kernel"):
            self.last_boot_index = 1

        qemu_binary = utils_misc.get_qemu_binary(params)

        self.qemu_binary = qemu_binary
        self.qemu_version = process.run("%s -version" % qemu_binary,
                                        verbose=False,
                                        ignore_status=True,
                                        shell=True).stdout_text.split(',')[0]
        support_cpu_model = to_text(process.run("%s -cpu \\?" % qemu_binary,
                                                verbose=False,
                                                ignore_status=True,
                                                shell=True).stdout,
                                    errors='replace')

        self.last_driver_index = 0
        # init the dict index_in_use
        for key in list(params.keys()):
            if 'drive_index' in key:
                self.index_in_use[params.get(key)] = True

        cmd = ""
        # Enable the use of glibc's malloc_perturb feature
        if params.get("malloc_perturb", "no") == "yes":
            cmd += "MALLOC_PERTURB_=1 "
        # Set the X11 display parameter if requested
        if params.get("x11_display"):
            cmd += "DISPLAY=%s " % params.get("x11_display")
        if params.get("qemu_audio_drv"):
            cmd += "QEMU_AUDIO_DRV=%s " % params.get("qemu_audio_drv")
        # Add command prefix for qemu-kvm. like taskset, valgrind and so on
        if params.get("qemu_command_prefix"):
            qemu_command_prefix = params.get("qemu_command_prefix")
            cmd += "%s " % qemu_command_prefix
        # Add numa memory cmd to pin guest memory to numa node
        if params.get("numa_node"):
            numa_node = int(params.get("numa_node"))
            if len(utils_misc.get_node_cpus()) < int(params.get("smp", 1)):
                LOG.info("Skip pinning, no enough nodes")
            elif numa_node < 0:
                n = utils_misc.NumaNode(numa_node)
                cmd += "numactl -m %s " % n.node_id
            else:
                n = numa_node - 1
                cmd += "numactl -m %s " % n

        # Start constructing devices representation
        devices = qcontainer.DevContainer(qemu_binary, self.name,
                                          params.get('strict_mode'),
                                          params.get(
                                              'workaround_qemu_qmp_crash'),
                                          params.get('allow_hotplugged_vm'))
        StrDev = qdevices.QStringDevice
        QDevice = qdevices.QDevice

        # update capabilities by users willingness
        if (params.get("qemu_force_use_drive_expression", "no") == "yes" and
                Flags.BLOCKDEV in devices.caps):
            devices.caps.clear_flag(Flags.BLOCKDEV)
        if (params.get("qemu_force_use_static_incoming_expression", "no") == "yes" and
                Flags.INCOMING_DEFER in devices.caps):
            devices.caps.clear_flag(Flags.INCOMING_DEFER)
        if (params.get("qemu_force_disable_migration_parameter", "no") == "yes" and
                Flags.MIGRATION_PARAMS in devices.caps):
            devices.caps.clear_flag(Flags.MIGRATION_PARAMS)

        devices.insert(StrDev('PREFIX', cmdline=cmd))
        # Add the qemu binary
        devices.insert(StrDev('qemu', cmdline=qemu_binary))
        qemu_stop = params.get("qemu_stop", "on")
        if qemu_stop == "on":
            devices.insert(StrDev('-S', cmdline="-S"))
        qemu_preconfig = params.get_boolean("qemu_preconfig")
        if qemu_preconfig:
            devices.insert(StrDev('preconfig', cmdline="--preconfig"))
        # Add the VM's name
        devices.insert(StrDev('vmname', cmdline=add_name(name)))

        qemu_sandbox = params.get("qemu_sandbox")
        if qemu_sandbox == "on":
            devices.insert(
                StrDev(
                    'qemu_sandbox',
                    cmdline=process_sandbox(
                        devices,
                        "add")))
        elif qemu_sandbox == "off":
            devices.insert(
                StrDev(
                    'qemu_sandbox',
                    cmdline=process_sandbox(
                        devices,
                        "rem")))
        del qemu_sandbox

        devs = devices.machine_by_params(params)
        devices.insert(devs)

        # no automagic devices please
        defaults = params.get("defaults", "no")
        if devices.has_option("nodefaults") and defaults != "yes":
            devices.insert(StrDev('nodefaults', cmdline=" -nodefaults"))

        # nodefconfig please
        if params.get("defconfig", "yes") == "no":
            devices.insert(StrDev('nodefconfig', cmdline=" -nodefconfig"))

        # Add device intel-iommu, it must be added before any virtio devices
        if (params.get('intel_iommu') == 'yes' and
                devices.has_device('intel-iommu')):
            iommu_params = {
                'intremap': params.get('iommu_intremap', 'on'),
                'device-iotlb': params.get('iommu_device_iotlb', 'on'),
                'caching-mode': params.get('iommu_caching_mode'),
                'eim': params.get('iommu_eim'),
                'x-buggy-eim': params.get('iommu_x_buggy_eim'),
                'version': params.get('iommu_version'),
                'x-scalable-mode': params.get('iommu_x_scalable_mode'),
                'dma-drain': params.get('iommu_dma_drain'),
                'pt': params.get('iommu_pt'),
                'aw-bits': params.get('iommu_aw_bits')}
            devices.insert(QDevice('intel-iommu', iommu_params))

        vga = params.get("vga")
        if vga:
            devices.insert(add_vga(devices, vga))
            if vga == 'qxl':
                qxl_dev_nr = int(params.get("qxl_dev_nr", 1))
                if qxl_dev_nr > 1:
                    addr = int(params.get("qxl_base_addr", 29))
                    cmdline = add_qxl(qxl_dev_nr, addr)
                    devices.insert(StrDev('qxl', cmdline=cmdline))

        # Add watchdog device
        if params.get("enable_watchdog", "no") == "yes":
            device_type = params.get("watchdog_device_type")
            action = params.get("watchdog_action", "reset")
            devices.insert(add_watchdog(devices, device_type, action))

        # When old scsi fmt is used, new device with lowest pci_addr is created
        devices.hook_fill_scsi_hbas(params)

        # Additional PCI RC/switch/bridges
        add_pci_controllers(devices, params)

        # Add Memory devices
        add_memorys(devices, params)
        mem = int(params.get("mem", 0))

        # Get cpu model, before add smp, to determine cpu topology
        cpu_model = params.get("cpu_model", "")
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
                LOG.error("Non existing CPU model %s will be passed "
                          "to qemu (wrong config or negative test)", model)

        if use_default_cpu_model:
            cpu_model = params.get("default_cpu_model", "")

        # Add smp
        smp = params.get_numeric('smp')
        vcpu_maxcpus = params.get_numeric("vcpu_maxcpus")
        vcpu_sockets = params.get_numeric("vcpu_sockets")
        vcpu_cores = params.get_numeric("vcpu_cores")
        vcpu_threads = params.get_numeric("vcpu_threads")
        vcpu_dies = params.get("vcpu_dies", 0)
        enable_dies = vcpu_dies != "INVALID" and Flags.SMP_DIES in devices.caps
        if not enable_dies:
            # Set dies=1 when computing missing values
            vcpu_dies = 1
        # PC target support SMP 'dies' parameter since qemu 4.1
        vcpu_dies = int(vcpu_dies)

        # Some versions of windows don't support more than 2 sockets of cpu,
        # here is a workaround to make all windows use only 2 sockets.
        if (vcpu_sockets and vcpu_sockets > 2 and
                params.get("os_type") == 'windows'):
            vcpu_sockets = 2

        amd_vendor_string = params.get("amd_vendor_string")
        if not amd_vendor_string:
            amd_vendor_string = "AuthenticAMD"
        if amd_vendor_string == cpu.get_cpu_vendor():
            # AMD cpu do not support multi threads besides EPYC
            if (params.get("test_negative_thread", "no") != "yes" and
                    not cpu_model.startswith('EPYC')):
                vcpu_threads = 1
                txt = "Set vcpu_threads to 1 for AMD non-EPYC cpu."
                LOG.warn(txt)

        smp_err = ""
        if vcpu_maxcpus != 0:
            smp_values = [vcpu_sockets, vcpu_dies, vcpu_cores, vcpu_threads]
            if smp_values.count(0) == 1:
                smp_values.remove(0)
                topology_product = reduce(mul, smp_values)
                if vcpu_maxcpus < topology_product:
                    smp_err = ("maxcpus(%d) must be equal to or greater than "
                               "topological product(%d)" % (vcpu_maxcpus,
                                                            topology_product))
                else:
                    missing_value, cpu_mod = divmod(vcpu_maxcpus, topology_product)
                    vcpu_maxcpus -= cpu_mod
                    vcpu_sockets = vcpu_sockets or missing_value
                    vcpu_dies = vcpu_dies or missing_value
                    vcpu_cores = vcpu_cores or missing_value
                    vcpu_threads = vcpu_threads or missing_value
            elif smp_values.count(0) > 1:
                if vcpu_maxcpus == 1 and max(smp_values) < 2:
                    vcpu_sockets = vcpu_dies = vcpu_cores = vcpu_threads = 1

            hotpluggable_cpus = len(params.objects("vcpu_devices"))
            if params["machine_type"].startswith("pseries"):
                hotpluggable_cpus *= vcpu_threads
            smp = smp or vcpu_maxcpus - hotpluggable_cpus
        else:
            if smp == 0 or vcpu_sockets == 0:
                vcpu_dies = vcpu_dies or 1
                vcpu_cores = vcpu_cores or 1
                vcpu_threads = vcpu_threads or 1
                if smp == 0:
                    vcpu_sockets = vcpu_sockets or 1
                    smp = vcpu_cores * vcpu_threads * vcpu_dies * vcpu_sockets
                else:
                    vcpu_sockets = smp // (vcpu_cores * vcpu_threads * vcpu_dies) or 1
            elif vcpu_dies == 0:
                vcpu_cores = vcpu_cores or 1
                vcpu_threads = vcpu_threads or 1
                vcpu_dies = smp // (vcpu_sockets * vcpu_cores * vcpu_threads) or 1
            elif vcpu_cores == 0:
                vcpu_threads = vcpu_threads or 1
                vcpu_cores = smp // (vcpu_sockets * vcpu_threads * vcpu_dies) or 1
            else:
                vcpu_threads = smp // (vcpu_cores * vcpu_sockets * vcpu_dies) or 1

            hotpluggable_cpus = len(params.objects("vcpu_devices"))
            if params["machine_type"].startswith("pseries"):
                hotpluggable_cpus *= vcpu_threads
            vcpu_maxcpus = smp
            smp -= hotpluggable_cpus

        if smp <= 0:
            smp_err = ("Number of hotpluggable vCPUs(%d) is greater "
                       "than or equal to the maxcpus(%d)."
                       % (hotpluggable_cpus, vcpu_maxcpus))
        if smp_err:
            raise virt_vm.VMSMPTopologyInvalidError(smp_err)

        self.cpuinfo.smp = smp
        self.cpuinfo.maxcpus = vcpu_maxcpus
        self.cpuinfo.cores = vcpu_cores
        self.cpuinfo.threads = vcpu_threads
        self.cpuinfo.sockets = vcpu_sockets
        if enable_dies:
            self.cpuinfo.dies = vcpu_dies
        devices.insert(StrDev('smp', cmdline=add_smp(devices)))

        # Add numa nodes
        numa_total_cpus = 0
        numa_total_mem = 0
        for numa_node in params.objects("guest_numa_nodes"):
            numa_params = params.object_params(numa_node)
            numa_mem = numa_params.get("numa_mem")
            numa_cpus = numa_params.get("numa_cpus")
            numa_nodeid = numa_params.get("numa_nodeid")
            numa_memdev = numa_params.get("numa_memdev")
            numa_initiator = numa_params.get("numa_initiator")
            if numa_mem is not None:
                numa_total_mem += int(numa_mem)
            if numa_cpus is not None:
                numa_total_cpus += len(utils_misc.cpu_str_to_list(numa_cpus))
            cmdline = add_numa_node(devices, numa_memdev, numa_mem,
                                    numa_cpus, numa_nodeid, numa_initiator)
            devices.insert(StrDev('numa', cmdline=cmdline))

        # add '-numa dist'
        if devices.has_option("numa dist,.*"):
            for numa_node in params.objects("guest_numa_nodes"):
                numa_params = params.object_params(numa_node)
                numa_nodeid = numa_params.get("numa_nodeid")
                numa_dist = ast.literal_eval(numa_params.get("numa_dist", "[]"))
                if numa_nodeid is None or not numa_dist:
                    continue
                for dst_distance in numa_dist:
                    cmd = " -numa dist,src=%s,dst=%s,val=%s"
                    cmd = cmd % (numa_nodeid, dst_distance[0], dst_distance[1])
                    devices.insert(StrDev('numa_dist', cmdline=cmd))

        for numa_cpu in params.objects("guest_numa_cpus"):
            numa_cpu_params = params.object_params(numa_cpu)
            numa_cpu_nodeid = numa_cpu_params.get("numa_cpu_nodeid")
            numa_cpu_socketid = numa_cpu_params.get("numa_cpu_socketid")
            numa_cpu_dieid = numa_cpu_params.get("numa_cpu_dieid")
            numa_cpu_coreid = numa_cpu_params.get("numa_cpu_coreid")
            numa_cpu_threadid = numa_cpu_params.get("numa_cpu_threadid")
            cmdline = add_numa_cpu(devices, numa_cpu_nodeid, numa_cpu_socketid,
                                   numa_cpu_dieid, numa_cpu_coreid,
                                   numa_cpu_threadid)
            devices.insert(StrDev('numa_cpu', cmdline=cmdline))

        if params.get("numa_consistency_check_cpu_mem", "no") == "yes":
            if (numa_total_cpus > vcpu_maxcpus or numa_total_mem > int(mem) or
                    len(params.objects("guest_numa_nodes")) > vcpu_maxcpus):
                LOG.debug("-numa need %s vcpu and %s memory. It is not "
                          "matched the -smp and -mem. The vcpu number "
                          "from -smp is %s, and memory size from -mem is"
                          " %s" % (numa_total_cpus, numa_total_mem,
                                   vcpu_maxcpus, mem))
                raise virt_vm.VMDeviceError("The numa node cfg can not fit"
                                            " smp and memory cfg.")

        # Add '-numa hmat-lb' and '-numa hmat-cache'
        if devices.has_option('numa hmat-lb,.*'):
            for numa_node in params.objects('guest_numa_nodes'):
                numa_params = params.object_params(numa_node)
                if not numa_params.get('numa_hmat_lb'):
                    continue
                nodeid = numa_params['numa_nodeid']
                initiator = numa_params.get('numa_initiator', nodeid)
                for hmat_lb in numa_params.objects('numa_hmat_lb'):
                    devices.insert(
                        devices.numa_hmat_lb_define_by_params(
                            nodeid, initiator, params.object_params(hmat_lb)))
                devices.insert(
                    devices.numa_hmat_cache_define_by_params(nodeid,
                                                             numa_params))

        # Add cpu model
        if cpu_model:
            family = params.get("cpu_family", "")
            flags = params.get("cpu_model_flags", "")
            vendor = params.get("cpu_model_vendor", "")
            self.cpuinfo.model = cpu_model
            self.cpuinfo.vendor = vendor
            self.cpuinfo.flags = flags
            self.cpuinfo.family = family
            cpu_driver = params.get("cpu_driver")
            if cpu_driver:
                try:
                    cpu_driver_items = cpu_driver.split("-")
                    ctype = cpu_driver_items[cpu_driver_items.index("cpu") - 1]
                    self.cpuinfo.qemu_type = ctype
                except ValueError:
                    LOG.warning("Can not assign cpuinfo.type, assign as"
                                " 'unknown'")
                    self.cpuinfo.qemu_type = "unknown"
            cmd = add_cpu_flags(devices, cpu_model, flags, vendor, family)
            devices.insert(StrDev('cpu', cmdline=cmd))

        # Add vcpu devices
        vcpu_bus = devices.get_buses({'aobject': 'vcpu'})
        if vcpu_bus and params.get("vcpu_devices"):
            vcpu_bus = vcpu_bus[0]
            vcpu_bus.initialize(self.cpuinfo)
            vcpu_devices = params.objects("vcpu_devices")
            params["vcpus_count"] = str(vcpu_bus.vcpus_count)

            for vcpu in vcpu_devices:
                vcpu_dev = devices.vcpu_device_define_by_params(params, vcpu)
                devices.insert(vcpu_dev)

        # -soundhw addresses are always the lowest after scsi
        soundhw = params.get("soundcards")
        if soundhw:
            parent_bus = self._get_pci_bus(params, "soundcard")
            if not devices.has_option('device') or soundhw == "all":
                for sndcard in ('AC97', 'ES1370', 'intel-hda'):
                    # Add all dummy PCI devices and the actual command below
                    devices.insert(StrDev("SND-%s" % sndcard,
                                          parent_bus=parent_bus))
                devices.insert(StrDev('SoundHW',
                                      cmdline="-soundhw %s" % soundhw))
            else:
                # TODO: Use QDevices for this and set the addresses properly
                for sound_device in soundhw.split(","):
                    if "hda" in sound_device:
                        devices.insert(QDevice('intel-hda',
                                               parent_bus=parent_bus))
                        devices.insert(QDevice('hda-duplex'))
                    elif sound_device in ["es1370", "ac97"]:
                        devices.insert(QDevice(sound_device.upper(),
                                               parent_bus=parent_bus))
                    else:
                        devices.insert(QDevice(sound_device,
                                               parent_bus=parent_bus))

        # Add monitors
        catch_monitor = params.get("catch_monitor")
        if catch_monitor:
            if catch_monitor not in params.get("monitors"):
                params["monitors"] += " %s" % catch_monitor
        for monitor_name in params.objects("monitors"):
            monitor_params = params.object_params(monitor_name)
            monitor_filename = qemu_monitor.get_monitor_filename(vm,
                                                                 monitor_name)
            if monitor_params.get("monitor_type") == "qmp":
                cmd = add_qmp_monitor(devices, monitor_name,
                                      monitor_filename)
                devices.insert(StrDev('QMP-%s' % monitor_name, cmdline=cmd))
            else:
                cmd = add_human_monitor(devices, monitor_name,
                                        monitor_filename)
                devices.insert(StrDev('HMP-%s' % monitor_name, cmdline=cmd))

        # Add pvpanic device
        if params.get("enable_pvpanic") == "yes":
            if 'aarch64' in params.get('vm_arch_name', arch.ARCH):
                pvpanic = 'pvpanic-pci'
            else:
                pvpanic = 'pvpanic'
            if not devices.has_device(pvpanic):
                LOG.warn("%s device is not supported", pvpanic)
            else:
                if pvpanic == 'pvpanic-pci':
                    pvpanic_dev = qdevices.QDevice(pvpanic,
                                                   parent_bus=self._get_pci_bus(
                                                       params, None, True))
                else:
                    pvpanic_params = {"backend": pvpanic}
                    ioport = params.get("ioport_pvpanic")
                    events = params.get("events_pvpanic")
                    if ioport:
                        pvpanic_params["ioport"] = ioport
                    if events:
                        pvpanic_params["events"] = events
                    pvpanic_dev = qdevices.QCustomDevice("device",
                                                         params=pvpanic_params,
                                                         backend="backend")
                pvpanic_dev.set_param("id", utils_misc.generate_random_id(),
                                      dynamic=True)
                devices.insert(pvpanic_dev)

        # Add vmcoreinfo device
        if params.get("vmcoreinfo") == "yes":
            if not devices.has_device("vmcoreinfo"):
                LOG.warn("vmcoreinfo device is not supported")
            else:
                vmcoreinfo_dev = qdevices.QDevice("vmcoreinfo")
                devices.insert(vmcoreinfo_dev)

        # Add serial console redirection
        self.virtio_ports = []
        serials = params.objects('serials')
        if serials:
            self.serial_session_device = serials[0]
            host = params.get('chardev_host', '127.0.0.1')
            free_ports = utils_misc.find_free_ports(
                5000, 5899, len(serials), host)
            reg_count = 0
        for index, serial in enumerate(serials):
            serial_params = params.object_params(serial)
            serial_filename = serial_params.get('chardev_path')
            if serial_filename:
                serial_dirname = os.path.dirname(serial_filename)
                if not os.path.isdir(serial_dirname):
                    os.makedirs(serial_dirname)
            else:
                serial_filename = vm.get_serial_console_filename(serial)
            # Workaround for console issue, details:
            # http://lists.gnu.org/archive/html/qemu-ppc/2013-10/msg00129.html
            if 'ppc' in params.get('vm_arch_name', arch.ARCH)\
                    and serial_params.get('serial_type') == 'spapr-vty':
                reg = 0x30000000 + 0x1000 * reg_count
                serial_params['serial_reg'] = hex(reg)
                reg_count += 1
            backend = serial_params.get('chardev_backend',
                                        'unix_socket')
            if backend in ['udp', 'tcp_socket']:
                serial_params['chardev_host'] = host
                serial_params['chardev_port'] = free_ports[index]
            prefix = serial_params.get('virtio_port_name_prefix')
            serial_name = serial_params.get('serial_name')
            if not serial_name:
                serial_name = prefix + str(len(self.virtio_ports))\
                    if prefix else serial
                serial_params['serial_name'] = serial_name
            if serial_params['serial_type'].startswith('pci'):
                serial_params['serial_bus'] = self._get_pci_bus(serial_params,
                                                                'serial', False)
            serial_devices = devices.serials_define_by_params(
                serial, serial_params, serial_filename)

            devices.insert(serial_devices)

            # Create virtio_ports (virtserialport and virtconsole)
            serial_type = serial_params['serial_type']
            if serial_type.startswith('virt'):
                if backend == "spicevmc":
                    serial_filename = 'dev%s' % serial
                if backend in ['udp', 'tcp_socket']:
                    serial_filename = (serial_params['chardev_host'],
                                       serial_params['chardev_port'])
                port_name = serial_devices[-1].get_param('name')
                if "console" in serial_type:
                    self.virtio_ports.append(qemu_virtio_port.VirtioConsole(
                        serial, port_name, serial_filename, backend))
                else:
                    self.virtio_ports.append(qemu_virtio_port.VirtioSerial(
                        serial, port_name, serial_filename, backend))

        # Add virtio-rng devices
        for virtio_rng in params.objects("virtio_rngs"):
            rng_params = params.object_params(virtio_rng)
            parent_bus = self._get_pci_bus(rng_params, "vio_rng", True)
            add_virtio_rng(devices, rng_params, parent_bus)

        # Add logging
        if params.get("enable_debugcon") == "yes":
            devices.insert(StrDev('isa-log', cmdline=add_log_seabios(devices)))
        if params.get("anaconda_log", "no") == "yes":
            parent_bus = self._get_pci_bus(params, None, True)
            add_log_anaconda(devices, parent_bus)

        # Add USB controllers
        usbs = params.objects("usbs")
        if not devices.has_option("device"):
            usbs = ("oldusb",)  # Old qemu, add only one controller '-usb'
        for usb_name in usbs:
            usb_params = params.object_params(usb_name)
            parent_bus = self._get_pci_bus(usb_params, "usbc", True)
            for dev in devices.usbc_by_params(usb_name, usb_params, parent_bus):
                devices.insert(dev)

        # Add usb devices
        for usb_dev in params.objects("usb_devices"):
            usb_dev_params = params.object_params(usb_dev)
            devices.insert(devices.usb_by_params(usb_dev, usb_dev_params))

        # initialize iothread manager
        devices.initialize_iothread_manager(params, self.cpuinfo)

        # Add object throttle group
        for group in params.objects("throttle_groups"):
            group_params = params.object_params(group)
            dev = devices.throttle_group_define_by_params(group_params, group)
            devices.insert(dev)

        # Add images (harddrives)
        for image_name in params.objects("images"):
            # FIXME: Use qemu_devices for handling indexes
            image_params = params.object_params(image_name)
            if image_params.get("boot_drive") == "no":
                continue
            if params.get("index_enable") == "yes":
                drive_index = image_params.get("drive_index")
                if drive_index:
                    index = drive_index
                else:
                    self.last_driver_index = get_index(self.last_driver_index)
                    index = str(self.last_driver_index)
                    self.last_driver_index += 1
            else:
                index = None
            image_bootindex = None
            image_boot = image_params.get("image_boot")
            if not re.search("boot=on\|off", devices.get_help_text(),
                             re.MULTILINE):
                if image_boot in ['yes', 'on', True]:
                    image_bootindex = str(self.last_boot_index)
                    self.last_boot_index += 1
                image_boot = "unused"
                image_bootindex = image_params.get('bootindex',
                                                   image_bootindex)
            else:
                if image_boot in ['yes', 'on', True]:
                    if self.last_boot_index > 0:
                        image_boot = False
                    self.last_boot_index += 1
            if ("virtio" in image_params.get("drive_format", "") or
                    "virtio" in image_params.get("scsi_hba", "")):
                parent_bus = self._get_pci_bus(image_params, "disk", True)
            else:
                parent_bus = self._get_pci_bus(image_params, "disk", False)
            devs = devices.images_define_by_params(image_name, image_params,
                                                   'disk', index, image_boot,
                                                   image_bootindex,
                                                   pci_bus=parent_bus)
            for _ in devs:
                devices.insert(_)

        # Add filesystems
        for fs_name in params.objects("filesystems"):
            fs_params = params.object_params(fs_name)
            devices.insert(devices.fs_define_by_params(fs_name, fs_params))

        # Networking
        redirs = []
        for redir_name in params.objects("redirs"):
            redir_params = params.object_params(redir_name)
            guest_port = int(redir_params.get("guest_port"))
            host_port = vm.redirs.get(guest_port)
            redirs += [(host_port, guest_port)]

        iov = 0
        for nic in vm.virtnet:
            nic_params = params.object_params(nic.nic_name)
            if nic_params.get('pci_assignable') == "no":
                script = nic_params.get("nic_script")
                downscript = nic_params.get("nic_downscript")
                vhost = nic_params.get("vhost")
                vhostforce = nic_params.get("vhostforce")
                script_dir = data_dir.get_data_dir()
                if script:
                    script = utils_misc.get_path(script_dir, script)
                if downscript:
                    downscript = utils_misc.get_path(script_dir, downscript)
                # setup nic parameters as needed
                # add_netdev if netdev_id not set
                nic = vm.add_nic(**dict(nic))
                # gather set values or None if unset
                vlan = int(nic.get('vlan'))
                netdev_id = nic.get('netdev_id')
                device_id = nic.get('device_id')
                mac = nic.get('mac')
                nic_model = nic.get("nic_model")
                nic_extra = nic.get("nic_extra_params")
                bootindex = nic_params.get("bootindex")
                netdev_extra = nic.get("netdev_extra_params")
                bootp = nic.get("bootp")
                add_queues = nic_params.get("add_queues", "no") == "yes"
                add_tapfd = nic_params.get("add_tapfd", "no") == "yes"
                add_vhostfd = nic_params.get("add_vhostfd", "no") == "yes"
                helper = nic_params.get("helper")
                tapfds_len = int(nic_params.get("tapfds_len", -1))
                vhostfds_len = int(nic_params.get("vhostfds_len", -1))
                if nic.get("tftp"):
                    tftp = utils_misc.get_path(root_dir, nic.get("tftp"))
                else:
                    tftp = None
                nettype = nic.get("nettype", "bridge")
                # don't force conversion add_nic()/add_net() optional parameter
                if 'tapfds' in nic:
                    tapfds = nic.tapfds
                else:
                    tapfds = None
                if 'vhostfds' in nic:
                    vhostfds = nic.vhostfds
                else:
                    vhostfds = None
                ifname = nic.get('ifname')
                queues = nic.get("queues", 1)
                # specify the number of MSI-X vectors that the card should have;
                # this option currently only affects virtio cards
                if nic_params.get("enable_msix_vectors") == "yes"\
                        and int(queues) != 1:
                    if "vectors" in nic:
                        vectors = nic.vectors
                    else:
                        vectors = 2 * int(queues) + 2
                else:
                    vectors = None

                # Setup some exclusive parameters if we are not running a
                # negative test.
                if nic_params.get("run_invalid_cmd_nic") != "yes":
                    if vhostfds or tapfds or add_queues:
                        helper = None
                    if vhostfds or tapfds:
                        add_queues = None
                    add_vhostfd = None
                    add_tapfd = None
                else:
                    if vhostfds and vhostfds_len > -1:
                        vhostfd_list = re.split(":", vhostfds)
                        if vhostfds_len < len(vhostfd_list):
                            vhostfds = ":".join(vhostfd_list[:vhostfds_len])
                    if tapfds and tapfds_len > -1:
                        tapfd_list = re.split(":", tapfds)
                        if tapfds_len < len(tapfd_list):
                            tapfds = ":".join(tapfd_list[:tapfds_len])

                # Handle the '-net nic' part
                if params.get("machine_type") != "q35":
                    pcie = False
                else:
                    pcie = nic_model not in ['e1000', 'rtl8139']
                parent_bus = self._get_pci_bus(nic_params, "nic", pcie)
                add_nic(devices, vlan, nic_model, mac,
                        device_id, netdev_id, nic_extra,
                        nic_params.get("nic_pci_addr"),
                        bootindex, queues, vectors, parent_bus,
                        nic_params.get("ctrl_mac_addr"),
                        nic_params.get("mq"),
                        nic_params.get("failover"))

                # Handle the '-net tap' or '-net user' or '-netdev' part
                cmd, cmd_nd = add_net(devices, vlan, nettype, ifname, tftp,
                                      bootp, redirs, netdev_id, netdev_extra,
                                      tapfds, script, downscript, vhost,
                                      queues, vhostfds, add_queues, helper,
                                      add_tapfd, add_vhostfd, vhostforce)

                if vhostfds is None:
                    vhostfds = ""

                if tapfds is None:
                    tapfds = ""

                net_params = {'netdev_id': netdev_id,
                              'vhostfd': vhostfds.split(":")[0],
                              'vhostfds': vhostfds,
                              'tapfd': tapfds.split(":")[0],
                              'tapfds': tapfds,
                              'ifname': ifname,
                              }

                for i, (host_port, guest_port) in enumerate(redirs):
                    net_params["host_port%d" % i] = host_port
                    net_params["guest_port%d" % i] = guest_port

                # TODO: Is every NIC a PCI device?
                devices.insert(StrDev("NET-%s" % nettype, cmdline=cmd,
                                      params=net_params, cmdline_nd=cmd_nd))
            else:
                device_driver = nic_params.get("device_driver", "pci-assign")
                failover_pair_id = nic_params.get("failover_pair_id")
                pci_id = vm.pa_pci_ids[iov]
                # On Power architecture using short id would result in
                # pci device lookup failure while writing vendor id to
                # stub_new_id/stub_remove_id. Instead we should be using
                # pci id as-is for vendor id.
                if arch.ARCH != 'ppc64le':
                    pci_id = ":".join(pci_id.split(":")[1:])

                add_pcidevice(devices, pci_id, params=nic_params,
                              device_driver=device_driver,
                              pci_bus=pci_bus)
                iov += 1

        # Add vsock device, cid 0-2 are reserved by system
        vsocks = params.objects('vsocks')
        if vsocks:
            linux_modules.load_module('vhost_vsock')
            min_cid = 3
            for vsock in vsocks:
                guest_cid = utils_vsock.get_guest_cid(min_cid)
                vsock_params = {"id": vsock, "guest-cid": guest_cid}
                if '-mmio:' in params.get('machine_type'):
                    dev_vsock = QDevice('vhost-vsock-device', vsock_params)
                elif params.get('machine_type').startswith("s390"):
                    dev_vsock = QDevice("vhost-vsock-ccw", vsock_params)
                else:
                    dev_vsock = QDevice('vhost-vsock-pci', vsock_params,
                                        parent_bus=pci_bus)
                devices.insert(dev_vsock)
                min_cid = guest_cid + 1

        # Add cdroms
        for cdrom in params.objects("cdroms"):
            image_params = params.object_params(cdrom)
            # FIXME: Use qemu_devices for handling indexes
            if image_params.get("boot_drive") == "no":
                continue
            if params.get("index_enable") == "yes":
                drive_index = image_params.get("drive_index")
                if drive_index:
                    index = drive_index
                else:
                    self.last_driver_index = get_index(self.last_driver_index)
                    index = str(self.last_driver_index)
                    self.last_driver_index += 1
            else:
                index = None
            image_bootindex = None
            image_boot = image_params.get("image_boot")
            if not re.search("boot=on\|off", devices.get_help_text(),
                             re.MULTILINE):
                if image_boot in ['yes', 'on', True]:
                    image_bootindex = str(self.last_boot_index)
                    self.last_boot_index += 1
                image_boot = "unused"
                image_bootindex = image_params.get(
                    'bootindex', image_bootindex)
            else:
                if image_boot in ['yes', 'on', True]:
                    if self.last_boot_index > 0:
                        image_boot = False
                    self.last_boot_index += 1
            iso = image_params.get("cdrom")
            if iso or image_params.get("cdrom_without_file") == "yes":
                if ("virtio" in image_params.get("driver_format", "") or
                        "virtio" in image_params.get("scsi_hba", "")):
                    parent_bus = self._get_pci_bus(image_params, "cdrom", True)
                else:
                    parent_bus = self._get_pci_bus(image_params, "cdrom", False)
                devs = devices.cdroms_define_by_params(cdrom, image_params,
                                                       'cdrom', index,
                                                       image_boot,
                                                       image_bootindex,
                                                       pci_bus=parent_bus)
                for _ in devs:
                    devices.insert(_)

        add_floppy(devices, params)

        tftp = params.get("tftp")
        if tftp:
            tftp = utils_misc.get_path(data_dir.get_data_dir(), tftp)
            devices.insert(StrDev('tftp', cmdline=add_tftp(devices, tftp)))

        bootp = params.get("bootp")
        if bootp:
            devices.insert(StrDev('bootp',
                                  cmdline=add_bootp(devices, bootp)))

        kernel = params.get("kernel")
        if kernel:
            kernel = utils_misc.get_path(data_dir.get_data_dir(), kernel)
            devices.insert(StrDev('kernel',
                                  cmdline=add_kernel(kernel)))

        kernel_params = params.get("kernel_params")
        if kernel_params:
            cmd = add_kernel_cmdline(kernel_params)
            devices.insert(StrDev('kernel-params', cmdline=cmd))

        initrd = params.get("initrd")
        if initrd:
            initrd = utils_misc.get_path(data_dir.get_data_dir(), initrd)
            devices.insert(StrDev('initrd',
                                  cmdline=add_initrd(initrd)))

        for host_port, guest_port in redirs:
            cmd = add_tcp_redir(devices, host_port, guest_port)
            devices.insert(StrDev('tcp-redir', cmdline=cmd))

        cmd = ""
        if params.get("display") == "vnc":
            vnc_extra_params = params.get("vnc_extra_params")
            vnc_password = params.get("vnc_password", "no")
            cmd += add_vnc(self.vnc_port, vnc_password, vnc_extra_params)
        elif params.get("display") == "sdl":
            cmd += add_sdl(devices)
        elif params.get("display") == "nographic":
            cmd += add_nographic()
        elif params.get("display") == "spice":
            spice_keys = (
                "spice_port", "spice_password", "spice_addr", "spice_ssl",
                "spice_tls_port", "spice_tls_ciphers", "spice_gen_x509",
                "spice_x509_dir", "spice_x509_prefix",
                "spice_x509_key_file", "spice_x509_cacert_file",
                "spice_x509_key_password", "spice_x509_secure",
                "spice_x509_cacert_subj", "spice_x509_server_subj",
                "spice_secure_channels", "spice_plaintext_channels",
                "spice_image_compression", "spice_jpeg_wan_compression",
                "spice_zlib_glz_wan_compression", "spice_streaming_video",
                "spice_agent_mouse", "spice_playback_compression",
                "spice_ipv4", "spice_ipv6", "spice_x509_cert_file",
                "disable_copy_paste", "spice_seamless_migration",
                "listening_addr"
            )
            for skey in spice_keys:
                value = params.get(skey, None)
                if value is not None:
                    # parameter can be defined as empty string in Cartesian
                    # config.  Example: spice_password =
                    spice_options[skey] = value
            cmd += add_spice(spice_options)
        if cmd:
            devices.insert(StrDev('display', cmdline=cmd))

        if params.get("uuid") == "random":
            cmd = add_uuid(vm.uuid)
            devices.insert(StrDev('uuid', cmdline=cmd))
        elif params.get("uuid"):
            cmd = add_uuid(params.get("uuid"))
            devices.insert(StrDev('uuid', cmdline=cmd))

        if params.get("testdev") == "yes":
            cmd = add_testdev(devices, vm.get_testlog_filename())
            devices.insert(StrDev('testdev', cmdline=cmd))

        if params.get("isa_debugexit") == "yes":
            iobase = params.get("isa_debugexit_iobase")
            iosize = params.get("isa_debugexit_iosize")
            cmd = add_isa_debug_exit(devices, iobase, iosize)
            devices.insert(StrDev('isa_debugexit', cmdline=cmd))

        if params.get("disable_hpet") == "yes":
            devices.insert(StrDev('nohpet', cmdline=add_no_hpet(devices)))

        devices.insert(StrDev('rtc', cmdline=add_rtc(devices)))

        if devices.has_option("boot"):
            boot_opts = {}
            boot_opts["menu"] = params.get("boot_menu")
            boot_opts["order"] = params.get("boot_order")
            boot_opts["once"] = params.get("boot_once")
            boot_opts["strict"] = params.get("boot_strict")
            boot_opts["reboot-timeout"] = params.get("boot_reboot_timeout")
            boot_opts["splash-time"] = params.get("boot_splash_time")
            cmd = add_boot(devices, boot_opts)
            devices.insert(StrDev('bootmenu', cmdline=cmd))

        p9_export_dir = params.get("9p_export_dir")
        if p9_export_dir:
            cmd = " -fsdev"
            p9_fs_driver = params.get("9p_fs_driver")
            if p9_fs_driver == "handle":
                cmd += " handle,id=local1,path=" + p9_export_dir
            elif p9_fs_driver == "proxy":
                cmd += " proxy,id=local1,socket="
            else:
                p9_fs_driver = "local"
                cmd += " local,id=local1,path=" + p9_export_dir

            # security model is needed only for local fs driver
            if p9_fs_driver == "local":
                p9_security_model = params.get("9p_security_model")
                if not p9_security_model:
                    p9_security_model = "none"
                cmd += ",security_model=" + p9_security_model
            elif p9_fs_driver == "proxy":
                p9_socket_name = params.get("9p_socket_name")
                if not p9_socket_name:
                    raise virt_vm.VMImageMissingError("Socket name not "
                                                      "defined")
                cmd += p9_socket_name

            p9_immediate_writeout = params.get("9p_immediate_writeout")
            if p9_immediate_writeout == "yes":
                cmd += ",writeout=immediate"

            p9_readonly = params.get("9p_readonly")
            if p9_readonly == "yes":
                cmd += ",readonly"

            devices.insert(StrDev('fsdev', cmdline=cmd))

            parent_bus = self._get_pci_bus(params, 'vio_9p', True)
            dev = QDevice('virtio-9p-pci', parent_bus=parent_bus)
            dev.set_param('fsdev', 'local1')
            dev.set_param('mount_tag', 'autotest_tag')
            devices.insert(dev)

        extra_params = params.get("extra_params")
        if extra_params:
            devices.insert(StrDev('extra', cmdline=extra_params))

        bios_path = params.get("bios_path")
        if bios_path:
            devices.insert(StrDev('bios', cmdline="-bios %s" % bios_path))

        # Add TPM devices
        for tpm in params.objects("tpms"):
            tpm_params = params.object_params(tpm)
            devices.insert(devices.tpm_define_by_params(tpm, tpm_params))

        disable_kvm_option = ""
        if (devices.has_option("no-kvm")):
            disable_kvm_option = "-no-kvm"

        enable_kvm_option = ""
        if (devices.has_option("enable-kvm")):
            enable_kvm_option = "-enable-kvm"

        if (params.get("disable_kvm", "no") == "yes"):
            params["enable_kvm"] = "no"

        if not params.get("vm_accelerator"):
            if (params.get("enable_kvm", "yes") == "no"):
                devices.insert(StrDev('nokvm', cmdline=disable_kvm_option))
                LOG.debug("qemu will run in TCG mode")
            else:
                devices.insert(StrDev('kvm', cmdline=enable_kvm_option))
                LOG.debug("qemu will run in KVM mode")

        compat = params.get("qemu_compat")
        if compat and devices.has_option("compat"):
            devices.insert(StrDev('compat', cmdline="-compat %s" % compat))

        self.no_shutdown = (devices.has_option("no-shutdown") and
                            params.get("disable_shutdown", "no") == "yes")
        if self.no_shutdown:
            devices.insert(StrDev('noshutdown', cmdline="-no-shutdown"))

        user_runas = params.get("user_runas")
        if devices.has_option("runas") and user_runas:
            devices.insert(StrDev('runas', cmdline="-runas %s" % user_runas))

        if params.get("enable_sga") == "yes":
            devices.insert(StrDev('sga', cmdline=add_sga(devices)))

        if params.get("smartcard", "no") == "yes":
            sc_chardev = params.get("smartcard_chardev")
            sc_id = params.get("smartcard_id")
            devices.insert(StrDev('smartcard',
                                  cmdline=add_smartcard(sc_chardev, sc_id)))

        option_roms = params.get("option_roms")
        if option_roms:
            cmd = ""
            for opt_rom in option_roms.split():
                cmd += add_option_rom(devices, opt_rom)
            if cmd:
                devices.insert(StrDev('ROM', cmdline=cmd))

        for input_device in params.objects("inputs"):
            devs = devices.input_define_by_params(params, input_device)
            devices.insert(devs)

        for balloon_device in params.objects("balloon"):
            balloon_params = params.object_params(balloon_device)
            balloon_devid = balloon_params.get("balloon_dev_devid")
            balloon_bus = None
            use_ofmt = balloon_params.get("balloon_use_old_format",
                                          "no") == "yes"
            if balloon_params.get("balloon_dev_add_bus") == "yes":
                balloon_bus = self._get_pci_bus(balloon_params, 'balloon', True)
            options = {}
            deflate_on_oom = balloon_params.get("balloon_opt_deflate_on_oom")
            options["deflate-on-oom"] = deflate_on_oom
            guest_polling = balloon_params.get("balloon_opt_guest_polling")
            options["guest-stats-polling-interval"] = guest_polling
            free_report = balloon_params.get("balloon_opt_free_page_reporting")
            options["free-page-reporting"] = free_report
            add_balloon(devices, devid=balloon_devid, bus=balloon_bus,
                        use_old_format=use_ofmt, options=options)

        # Add qemu options
        if params.get("msg_timestamp"):
            attr_info = ["timestamp", params["msg_timestamp"], bool]
            add_qemu_option(devices, "msg", [attr_info])
        if params.get("realtime_mlock"):
            if devices.has_option("overcommit"):
                attr_info = ["mem-lock", params["realtime_mlock"], bool]
                add_qemu_option(devices, "overcommit", [attr_info])
            else:
                attr_info = ["mlock", params["realtime_mlock"], bool]
                add_qemu_option(devices, "realtime", [attr_info])
        if params.get("cpu-pm"):
            if devices.has_option("overcommit"):
                attr_info = ["cpu-pm", params["cpu-pm"], bool]
                add_qemu_option(devices, "overcommit", [attr_info])
        if params.get("keyboard_layout"):
            attr_info = [None, params["keyboard_layout"], None]
            add_qemu_option(devices, "k", [attr_info])

        # Add options for all virtio devices
        virtio_devices = filter(lambda x: re.search(r"(?:^virtio-)|(?:^vhost-)",
                                                    x.get_param('driver', '')),
                                devices)
        for device in virtio_devices:
            dev_type = device.get_param("driver")
            # Currently virtio1.0 behaviour on latest RHEL.7.2/RHEL.7.3
            # qemu versions is default, we don't need to specify the
            # disable-legacy and disable-modern options explicitly.
            dev_info = devices.execute_qemu("-device %s,help" % dev_type)
            dev_properties = re.findall(r"([a-zA-Z0-9_-]+)=\S+", dev_info)
            properties_to_be_set = {
                "disable-legacy": params.get("virtio_dev_disable_legacy"),
                "disable-modern": params.get("virtio_dev_disable_modern"),
                "iommu_platform": params.get("virtio_dev_iommu_platform"),
                "ats": params.get("virtio_dev_ats"),
                "aer": params.get("virtio_dev_aer")}
            for key, value in properties_to_be_set.items():
                if value and key in dev_properties:
                    device.set_param(key, value)

        # Add extra root_port at the end of the command line only if there is
        # free slot on pci.0, discarding them otherwise
        func_0_addr = None
        pcic_params = {'type': 'pcie-root-port'}
        extra_port_num = int(params.get('pcie_extra_root_port', 0))
        for num in range(extra_port_num):
            try:
                # enable multifunction for root port
                port_name = "pcie_extra_root_port_%d" % num
                root_port = devices.pcic_by_params(port_name, pcic_params)
                pcie_root_port_params = params.get('pcie_root_port_params')
                if pcie_root_port_params:
                    for extra_param in pcie_root_port_params.split(","):
                        key, value = extra_param.split('=')
                        root_port.set_param(key, value)
                func_num = num % 8
                if func_num == 0:
                    root_port.set_param('multifunction', 'on')
                    devices.insert(root_port)
                    func_0_addr = root_port.get_param('addr')
                else:
                    port_addr = '%s.%s' % (func_0_addr, hex(func_num))
                    root_port.set_param('addr', port_addr)
                    devices.insert(root_port)
            except DeviceError:
                LOG.warning("No sufficient free slot for extra"
                            " root port, discarding %d of them"
                            % (extra_port_num - num))
                break
        return devices, spice_options

    def _del_port_from_bridge(self, nic):
        br_mgr, br_name = utils_net.find_current_bridge(nic.ifname)
        if br_name == nic.netdst:
            br_mgr.del_port(nic.netdst, nic.ifname)

    def _nic_tap_add_helper(self, nic):
        if nic.nettype == 'macvtap':
            macvtap_mode = self.params.get("macvtap_mode", "vepa")
            nic.tapfds = utils_net.create_and_open_macvtap(nic.ifname,
                                                           macvtap_mode,
                                                           nic.queues,
                                                           nic.netdst,
                                                           nic.mac)
        else:
            nic.tapfds = utils_net.open_tap("/dev/net/tun", nic.ifname,
                                            queues=nic.queues, vnet_hdr=True)
            LOG.debug("Adding VM %s NIC ifname %s to bridge %s",
                      self.name, nic.ifname, nic.netdst)
            if nic.nettype == 'bridge':
                utils_net.add_to_bridge(nic.ifname, nic.netdst)
        utils_net.bring_up_ifname(nic.ifname)

    def _nic_tap_remove_helper(self, nic):
        try:
            if nic.nettype == 'macvtap':
                LOG.info("Remove macvtap ifname %s", nic.ifname)
                tap = utils_net.Macvtap(nic.ifname)
                tap.delete()
            else:
                LOG.debug("Removing VM %s NIC ifname %s from bridge %s",
                          self.name, nic.ifname, nic.netdst)
                if nic.tapfds:
                    for i in nic.tapfds.split(':'):
                        os.close(int(i))
                if nic.vhostfds:
                    for i in nic.vhostfds.split(':'):
                        os.close(int(i))
                if nic.ifname:
                    deletion_time = max(5, math.ceil(int(nic.queues) / 8))
                    if utils_misc.wait_for(lambda: nic.ifname not in utils_net.get_net_if(),
                                           deletion_time):
                        self._del_port_from_bridge(nic)
        except TypeError:
            pass

    def _create_serial_console(self):
        """
        Establish a session with the serial console.

        Let's consider the first serial port as serial console.
        Note: requires a version of netcat that supports -U
        """
        if self.serial_session_device is None:
            LOG.warning("No serial ports defined!")
            return
        log_name = "serial-%s-%s.log" % (
            self.serial_session_device, self.name)
        self.serial_console_log = os.path.join(utils_misc.get_log_file_dir(),
                                               log_name)
        file_name = self.get_serial_console_filename(
            self.serial_session_device)
        self.serial_console = aexpect.ShellSession(
            "nc -U %s" % file_name,
            auto_close=False,
            output_func=utils_misc.log_line,
            output_params=(log_name,),
            prompt=self.params.get("shell_prompt", "[\#\$]"),
            status_test_command=self.params.get("status_test_command",
                                                "echo $?"))

    def update_system_dependent_devs(self):
        # Networking
        devices = self.devices
        params = self.params
        redirs = []
        for redir_name in params.objects("redirs"):
            redir_params = params.object_params(redir_name)
            guest_port = int(redir_params.get("guest_port"))
            host_port = self.redirs.get(guest_port)
            redirs += [(host_port, guest_port)]

        for nic in self.virtnet:
            nic_params = params.object_params(nic.nic_name)
            if nic_params.get('pci_assignable') == "no":
                script = nic_params.get("nic_script")
                downscript = nic_params.get("nic_downscript")
                script_dir = data_dir.get_data_dir()
                if script:
                    script = utils_misc.get_path(script_dir, script)
                if downscript:
                    downscript = utils_misc.get_path(script_dir,
                                                     downscript)
                # setup nic parameters as needed
                # add_netdev if netdev_id not set
                nic = self.add_nic(**dict(nic))
                # gather set values or None if unset
                netdev_id = nic.get('netdev_id')
                # don't force conversion add_nic()/add_net() optional
                # parameter
                if 'tapfds' in nic:
                    tapfds = nic.tapfds
                else:
                    tapfds = ""
                if 'vhostfds' in nic:
                    vhostfds = nic.vhostfds
                else:
                    vhostfds = ""
                ifname = nic.get('ifname')
                # specify the number of MSI-X vectors that the card should
                # have this option currently only affects virtio cards

                net_params = {'netdev_id': netdev_id,
                              'vhostfd': vhostfds.split(":")[0],
                              'vhostfds': vhostfds,
                              'tapfd': tapfds.split(":")[0],
                              'tapfds': tapfds,
                              'ifname': ifname,
                              }

                for i, (host_port, guest_port) in enumerate(redirs):
                    net_params["host_port%d" % i] = host_port
                    net_params["guest_port%d" % i] = guest_port

                # TODO: Is every NIC a PCI device?
                devs = devices.get_by_params({'netdev_id': netdev_id})
                # TODO: Is every NIC a PCI device?
                if len(devs) > 1:
                    LOG.error("There are %d devices with netdev_id %s."
                              " This shouldn't happens." % (len(devs),
                                                            netdev_id))
                devs[0].params.update(net_params)

    def update_vga_global_default(self, params, migrate=None):
        """
        Update VGA global default settings

        :param params: dict for create vm
        :param migrate: is vm create for migration
        """
        if not self.devices:
            return

        vga_mapping = {'VGA-std': 'VGA',
                       'VGA-cirrus': 'cirrus-vga',
                       'VGA-qxl': 'qxl-vga',
                       'qxl': 'qxl',
                       'VGA-none': None}
        for device in self.devices:
            if not isinstance(device, qdevices.QStringDevice):
                continue

            vga_type = vga_mapping.get(device.type)
            if not vga_type:
                continue

            help_cmd = '%s -device %s,\? 2>&1' % (self.qemu_binary, vga_type)
            help_info = process.run(help_cmd, shell=True,
                                    verbose=False).stdout_Text
            for pro in re.findall(r'%s.(\w+)=' % vga_type, help_info):
                key = [vga_type.lower(), pro]
                if migrate:
                    key.append('dst')
                key = '_'.join(key)
                val = params.get(key)
                if not val:
                    continue
                qdev = qdevices.QGlobal(vga_type, pro, val)
                self.devices.insert(qdev)

    @property
    def qmp_monitors(self):
        return [m for m in self.monitors if m.protocol == 'qmp']

    @property
    def spice_port(self):
        LOG.warning("'VM.spice_port' will be removed by the end of "
                    "the year 2017, please use 'self.spice_options."
                    "get(\"spice_port\")' instead")
        return self.spice_options.get("spice_port")

    @property
    def spice_tls_port(self):
        LOG.warning("'VM.spice_tls_port' will be removed by the end of "
                    "the year 2017, please use 'self.spice_options."
                    "get(\"spice_tls_port\")' instead")
        return self.spice_options.get("spice_tls_port")

    @error_context.context_aware
    def create(self, name=None, params=None, root_dir=None,
               timeout=120, migration_mode=None,
               migration_exec_cmd=None, migration_fd=None,
               mac_source=None):
        """
        Start the VM by running a qemu command.
        All parameters are optional. If name, params or root_dir are not
        supplied, the respective values stored as class attributes are used.

        :param name: The name of the object
        :param params: A dict containing VM params
        :param root_dir: Base directory for relative filenames
        :param migration_mode: If supplied, start VM for incoming migration
                using this protocol (either 'rdma', 'x-rdma', 'rdma', 'tcp', 'unix' or 'exec')
        :param migration_exec_cmd: Command to embed in '-incoming "exec: ..."'
                (e.g. 'gzip -c -d filename') if migration_mode is 'exec'
                default to listening on a random TCP port
        :param migration_fd: Open descriptor from machine should migrate.
        :param mac_source: A VM object from which to copy MAC addresses. If not
                specified, new addresses will be generated.

        :raise VMCreateError: If qemu terminates unexpectedly
        :raise VMKVMInitError: If KVM initialization fails
        :raise VMHugePageError: If hugepage initialization fails
        :raise VMImageMissingError: If a CD image is missing
        :raise VMHashMismatchError: If a CD image hash has doesn't match the
                expected hash
        :raise VMBadPATypeError: If an unsupported PCI assignment type is
                requested
        :raise VMPAError: If no PCI assignable devices could be assigned
        :raise TAPCreationError: If fail to create tap fd
        :raise BRAddIfError: If fail to add a tap to a bridge
        :raise TAPBringUpError: If fail to bring up a tap
        :raise PrivateBridgeError: If fail to bring the private bridge
        """
        error_context.context("creating '%s'" % self.name)
        self.destroy(free_mac_addresses=False)

        if name is not None:
            self.name = name
            self.devices = None     # Representation changed
        if params is not None:
            self.params = params
            self.devices = None     # Representation changed
        if root_dir is not None:
            self.root_dir = root_dir
            self.devices = None     # Representation changed
        name = self.name
        params = self.params
        root_dir = self.root_dir
        pass_fds = []
        if migration_fd:
            pass_fds.append(int(migration_fd))

        # Verify the md5sum of the ISO images
        for cdrom in params.objects("cdroms"):
            cdrom_params = params.object_params(cdrom)
            if cdrom_params.get("enable_gluster") == "yes":
                continue
            if cdrom_params.get("enable_ceph") == "yes":
                continue
            if cdrom_params.get("enable_iscsi") == "yes":
                continue
            if cdrom_params.get("enable_nbd") == "yes":
                continue
            if cdrom_params.get("enable_nvme") == "yes":
                continue
            if cdrom_params.get("enable_ssh") == "yes":
                continue

            iso = storage.get_iso_filename(cdrom_params,
                                           data_dir.get_data_dir())
            if iso:
                if not storage.file_exists(cdrom_params, iso):
                    raise virt_vm.VMImageMissingError(iso)

                compare = False
                if cdrom_params.get("skip_hash", "no") == "yes":
                    LOG.debug("Skipping hash comparison")
                elif cdrom_params.get("md5sum_1m"):
                    LOG.debug("Comparing expected MD5 sum with MD5 sum of "
                              "first MB of ISO file...")
                    actual_hash = crypto.hash_file(iso, 1048576,
                                                   algorithm="md5")
                    expected_hash = cdrom_params.get("md5sum_1m")
                    compare = True
                elif cdrom_params.get("md5sum"):
                    LOG.debug("Comparing expected MD5 sum with MD5 sum of "
                              "ISO file...")
                    actual_hash = crypto.hash_file(iso, algorithm="md5")
                    expected_hash = cdrom_params.get("md5sum")
                    compare = True
                elif cdrom_params.get("sha1sum"):
                    LOG.debug("Comparing expected SHA1 sum with SHA1 sum "
                              "of ISO file...")
                    actual_hash = crypto.hash_file(iso, algorithm="sha1")
                    expected_hash = cdrom_params.get("sha1sum")
                    compare = True
                if compare:
                    if actual_hash == expected_hash:
                        LOG.debug("Hashes match")
                    else:
                        raise virt_vm.VMHashMismatchError(actual_hash,
                                                          expected_hash)

        # Make sure the following code is not executed by more than one thread
        # at the same time
        lockfile = open(CREATE_LOCK_FILENAME, "w+")
        fcntl.lockf(lockfile, fcntl.LOCK_EX)

        try:
            # Handle port redirections
            redir_names = params.objects("redirs")
            host_ports = utils_misc.find_free_ports(
                5000, 5899, len(redir_names))

            old_redirs = {}
            if self.redirs:
                old_redirs = self.redirs

            self.redirs = {}
            for i in range(len(redir_names)):
                redir_params = params.object_params(redir_names[i])
                guest_port = int(redir_params.get("guest_port"))
                self.redirs[guest_port] = host_ports[i]

            if self.redirs != old_redirs:
                self.devices = None

            # Update the network related parameters as well to conform to
            # expected behavior on VM creation
            getattr(self, 'virtnet').__init__(self.params,
                                              self.name,
                                              self.instance)

            # Generate basic parameter values for all NICs and create TAP fd
            for nic in self.virtnet:
                nic_params = params.object_params(nic.nic_name)
                pa_type = nic_params.get("pci_assignable")
                if pa_type and pa_type != "no":
                    device_driver = nic_params.get("device_driver",
                                                   "pci-assign")
                    if "mac" not in nic:
                        self.virtnet.generate_mac_address(nic["nic_name"])
                    mac = nic["mac"]
                    if self.pci_assignable is None:
                        self.pci_assignable = test_setup.PciAssignable(
                            driver=params.get("driver"),
                            driver_option=params.get("driver_option"),
                            host_set_flag=params.get("host_setup_flag"),
                            kvm_params=params.get("kvm_default"),
                            vf_filter_re=params.get("vf_filter_re"),
                            pf_filter_re=params.get("pf_filter_re"),
                            device_driver=device_driver,
                            nic_name_re=params.get("nic_name_re"),
                            static_ip=int(params.get("static_ip", 0)),
                            start_addr_PF=params.get("start_addr_PF", None),
                            net_mask=params.get("net_mask", None),
                            pa_type=pa_type)

                    if nic_params.get("device_name", "").startswith("shell:"):
                        name = process.run(
                            nic_params.get("device_name").split(':', 1)[1],
                            shell=True).stdout_text
                    else:
                        name = nic_params.get("device_name")
                    # Virtual Functions (VF) assignable devices
                    if pa_type == "vf":
                        self.pci_assignable.add_device(device_type=pa_type,
                                                       mac=mac,
                                                       name=name)
                    # Physical NIC (PF) assignable devices
                    elif pa_type == "pf":
                        self.pci_assignable.add_device(device_type=pa_type,
                                                       name=name)
                    else:
                        raise virt_vm.VMBadPATypeError(pa_type)
                else:
                    # fill in key values, validate nettype
                    # note: make_create_command() calls vm.add_nic (i.e. on a
                    # copy)
                    if nic_params.get('netdst') == 'private':
                        nic.netdst = (test_setup.
                                      PrivateBridgeConfig(nic_params).brname)

                    nic = self.add_nic(**dict(nic))  # implied add_netdev

                    if mac_source:
                        # Will raise exception if source doesn't
                        # have corresponding nic
                        LOG.debug("Copying mac for nic %s from VM %s"
                                  % (nic.nic_name, mac_source.name))
                        nic.mac = mac_source.get_mac_address(nic.nic_name)

                    if nic.ifname in utils_net.get_net_if():
                        self.virtnet.generate_ifname(nic.nic_name)
                    else:
                        self._del_port_from_bridge(nic)

                    if nic.nettype in ['bridge', 'network', 'macvtap']:
                        self._nic_tap_add_helper(nic)
                        if bool(nic.tapfds):
                            for fd in nic.tapfds.split(':'):
                                pass_fds.append(int(fd))

                    if ((nic_params.get("vhost") in ['on',
                                                     'force',
                                                     'vhost=on']) and
                            (nic_params.get("enable_vhostfd", "yes") == "yes")):
                        vhostfds = []
                        for i in xrange(int(nic.queues)):
                            vhostfds.append(str(os.open("/dev/vhost-net",
                                                        os.O_RDWR)))
                        nic.vhostfds = ':'.join(vhostfds)
                        for fd in vhostfds:
                            pass_fds.append(int(fd))
                    elif nic.nettype == 'user':
                        LOG.info("Assuming dependencies met for "
                                 "user mode nic %s, and ready to go"
                                 % nic.nic_name)
                    # Update the fd and vhostfd for nic devices
                    if self.devices is not None:
                        for device in self.devices:
                            cmd = device.cmdline()
                            if cmd is not None and "fd=" in cmd:
                                new_cmd = ""
                                for opt in cmd.split(","):
                                    if re.match('fd=', opt):
                                        opt = 'fd=%s' % nic.tapfds
                                    if re.match('vhostfd=', opt):
                                        opt = 'vhostfd=%s' % nic.vhostfds
                                    new_cmd += "%s," % opt
                                device._cmdline = new_cmd.rstrip(",")

                    self.virtnet.update_db()

            # Find available VNC port, if needed
            if params.get("display") == "vnc":
                self.vnc_port = utils_misc.find_free_port(5900, 6900, sequent=True)

            # Find random UUID if specified 'uuid = random' in config file
            if params.get("uuid") == "random":
                f = open("/proc/sys/kernel/random/uuid")
                self.uuid = f.read().strip()
                f.close()

            if self.pci_assignable is not None:
                self.pa_pci_ids = self.pci_assignable.request_devs()

                if self.pa_pci_ids:
                    LOG.debug("Successfully assigned devices: %s",
                              self.pa_pci_ids)
                else:
                    raise virt_vm.VMPAError(pa_type)

            # Create serial ports.
            for serial in params.objects('serials'):
                serial_params = params.object_params(serial)
                serial_type = serial_params["serial_type"]
                if not serial_type.startswith('virt'):
                    self.serial_ports.append(serial)

            if (name is None and params is None and root_dir is None and
                    self.devices is not None):
                self.update_system_dependent_devs()
            # Make qemu command
            try:
                self.devices, self.spice_options = self.make_create_command()
                self.update_vga_global_default(params, migration_mode)
                LOG.debug(self.devices.str_short())
                LOG.debug(self.devices.str_bus_short())
                qemu_command = self.devices.cmdline()
            except (exceptions.TestSkipError, exceptions.TestCancel):
                # TestSkipErrors should be kept as-is so we generate SKIP
                # results instead of bogus FAIL results
                raise
            except Exception:
                for nic in self.virtnet:
                    self._nic_tap_remove_helper(nic)
                utils_misc.log_last_traceback('Fail to create qemu command:')
                raise virt_vm.VMStartError(self.name, 'Error occurred while '
                                           'executing make_create_command(). '
                                           'Check the log for traceback.')

            # Add migration parameters if required
            if migration_mode in ["tcp", "rdma", "x-rdma"]:
                self.migration_port = utils_misc.find_free_port(5200, 5899)
                incoming_val = (" -incoming " + migration_mode +
                                ":0:%d" % self.migration_port)
                if Flags.INCOMING_DEFER in self.devices.caps:
                    incoming_val = ' -incoming defer'
                    self.deferral_incoming = True
                qemu_command += incoming_val
            elif migration_mode == "unix":
                self.migration_file = os.path.join(data_dir.get_tmp_dir(),
                                                   "migration-unix-%s" %
                                                   self.instance)
                incoming_val = " -incoming unix:%s" % self.migration_file
                if Flags.INCOMING_DEFER in self.devices.caps:
                    incoming_val = ' -incoming defer'
                    self.deferral_incoming = True
                qemu_command += incoming_val
            elif migration_mode == "exec":
                if migration_exec_cmd is None:
                    self.migration_port = utils_misc.find_free_port(5200, 5899)
                    # check whether ip version supported by nc
                    if process.system("nc -h | grep -E '\-4 | \-6'",
                                      shell=True, ignore_status=True) == 0:
                        qemu_command += (' -incoming "exec:nc -l -%s %s"' %
                                         (self.ip_version[-1],
                                          self.migration_port))
                    else:
                        qemu_command += (' -incoming "exec:nc -l %s"' %
                                         self.migration_port)
                else:
                    qemu_command += (' -incoming "exec:%s"' %
                                     migration_exec_cmd)
            elif migration_mode == "fd":
                qemu_command += ' -incoming "fd:%d"' % (migration_fd)

            p9_fs_driver = params.get("9p_fs_driver")
            if p9_fs_driver == "proxy":
                proxy_helper_name = params.get("9p_proxy_binary",
                                               "virtfs-proxy-helper")
                proxy_helper_cmd = utils_misc.get_path(root_dir,
                                                       proxy_helper_name)
                if not proxy_helper_cmd:
                    raise virt_vm.VMConfigMissingError(self.name,
                                                       "9p_proxy_binary")

                p9_export_dir = params.get("9p_export_dir")
                if not p9_export_dir:
                    raise virt_vm.VMConfigMissingError(self.name,
                                                       "9p_export_dir")

                proxy_helper_cmd += " -p " + p9_export_dir
                proxy_helper_cmd += " -u 0 -g 0"
                p9_socket_name = params.get("9p_socket_name")
                proxy_helper_cmd += " -s " + p9_socket_name
                proxy_helper_cmd += " -n"

                LOG.info("Running Proxy Helper:\n%s", proxy_helper_cmd)
                self.process = aexpect.run_tail(proxy_helper_cmd,
                                                None,
                                                _picklable_logger,
                                                "[9p proxy helper]",
                                                auto_close=False)
            else:
                LOG.info("Running qemu command (reformatted):\n%s",
                         qemu_command.replace(" -", " \\\n    -"))
                self.qemu_command = qemu_command
                monitor_exit_status = \
                    params.get("vm_monitor_exit_status", "yes") == "yes"
                self.process = aexpect.run_tail(
                    qemu_command,
                    partial(qemu_proc_term_handler, self,
                            monitor_exit_status),
                    _picklable_logger, "[qemu output] ",
                    auto_close=False, pass_fds=pass_fds)

            LOG.info("Created qemu process with parent PID %d",
                     self.process.get_pid())
            self.start_time = time.time()
            self.start_monotonic_time = utils_misc.monotonic_time()

            # test doesn't need to hold tapfd's open
            for nic in self.virtnet:
                if 'tapfds' in nic:  # implies bridge/tap
                    try:
                        for i in nic.tapfds.split(':'):
                            os.close(int(i))
                        # qemu process retains access via open file
                        # remove this attribute from virtnet because
                        # fd numbers are not always predictable and
                        # vm instance must support cloning.
                        del nic['tapfds']
                    # File descriptor is already closed
                    except OSError:
                        pass
                if 'vhostfds' in nic:
                    try:
                        for i in nic.vhostfds.split(':'):
                            os.close(int(i))
                        del nic['vhostfds']
                    except OSError:
                        pass

            # Make sure qemu is not defunct
            if self.process.is_defunct():
                LOG.error("Bad things happened, qemu process is defunct")
                err = ("Qemu is defunct.\nQemu output:\n%s"
                       % self.process.get_output())
                self.destroy()
                raise virt_vm.VMStartError(self.name, err)

            # Make sure the process was started successfully
            if not self.process.is_alive():
                status = self.process.get_status()
                output = self.process.get_output().strip()
                migration_in_course = migration_mode is not None
                unknown_protocol = "unknown migration protocol" in output
                if migration_in_course and unknown_protocol:
                    e = VMMigrateProtoUnsupportedError(migration_mode, output)
                else:
                    e = virt_vm.VMCreateError(qemu_command, status, output)
                self.destroy()
                raise e

            # Establish monitor connections
            self.monitors = []
            for m_name in params.objects("monitors"):
                m_params = params.object_params(m_name)
                if m_params.get("debugonly", "no") == "yes":
                    continue
                try:
                    monitor = qemu_monitor.wait_for_create_monitor(self,
                                                                   m_name,
                                                                   m_params,
                                                                   timeout)
                except qemu_monitor.MonitorConnectError as detail:
                    LOG.error(detail)
                    self.destroy()
                    raise

                # Add this monitor to the list
                self.monitors.append(monitor)

            # Get the output so far, to see if we have any problems with
            # KVM modules or with hugepage setup.
            output = self.process.get_output()

            if re.search("Could not initialize KVM", output, re.IGNORECASE):
                e = virt_vm.VMKVMInitError(
                    qemu_command, self.process.get_output())
                self.destroy()
                raise e

            if "alloc_mem_area" in output:
                e = virt_vm.VMHugePageError(
                    qemu_command, self.process.get_output())
                self.destroy()
                raise e

            LOG.debug("VM appears to be alive with PID %s", self.get_pid())
            # Record vcpu infos in debug log
            is_preconfig = params.get_boolean("qemu_preconfig")
            if not is_preconfig:
                self.get_vcpu_pids(debug=True)
            vhost_thread_pattern = params.get("vhost_thread_pattern",
                                              r"\w+\s+(\d+)\s.*\[vhost-%s\]")
            self.vhost_threads = self.get_vhost_threads(vhost_thread_pattern)

            self.create_serial_console()

            for key, value in list(self.logs.items()):
                outfile = "%s-%s.log" % (key, name)
                self.logsessions[key] = aexpect.Tail(
                    "nc -U %s" % value,
                    auto_close=False,
                    output_func=utils_misc.log_line,
                    output_params=(outfile,))
                self.logsessions[key].set_log_file(outfile)

            # Wait for IO channels setting up completely,
            # such as serial console.
            time.sleep(1)

            if is_preconfig:
                return

            if params.get("paused_after_start_vm") != "yes":
                # start guest
                if self.monitor.verify_status("paused"):
                    if not migration_mode:
                        self.resume()

            # Update mac and IP info for assigned device
            # NeedFix: Can we find another way to get guest ip?
            if params.get("mac_changeable") == "yes":
                utils_net.update_mac_ip_address(self)

        finally:
            fcntl.lockf(lockfile, fcntl.LOCK_UN)
            lockfile.close()

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
        return utils_misc.wait_for(lambda: self.monitor.verify_status(status),
                                   timeout, first, step, text)

    def wait_until_paused(self, timeout):
        """
        Wait until the VM is paused.

        :param timeout: Timeout in seconds.

        :return: True in case the VM is paused before timeout, otherwise
                 return None.
        """
        return self.wait_for_status("paused", timeout)

    def wait_until_dead(self, timeout, first=0.0, step=1.0):
        """
        Wait until VM is dead.

        :return: True if VM is dead before timeout, otherwise returns None.

        :param timeout: Timeout in seconds
        :param first: Time to sleep before first attempt
        :param steps: Time to sleep between attempts in seconds
        """
        return utils_misc.wait_for(self.is_dead, timeout, first, step)

    def wait_for_shutdown(self, timeout=60):
        """
        Wait until guest shuts down.

        Helps until the VM is shut down by the guest.

        :return: True in case the VM was shut down, None otherwise.

        Note that the VM is not necessarily dead when this function returns
        True. If QEMU is running in -no-shutdown mode, the QEMU process
        may be still alive.
        """
        if self.no_shutdown:
            return self.wait_until_paused(timeout)
        else:
            return self.wait_until_dead(timeout, 1, 1)

    def graceful_shutdown(self, timeout=60):
        """
        Try to gracefully shut down the VM.

        :return: True if VM was successfully shut down, None otherwise.

        Note that the VM is not necessarily dead when this function returns
        True. If QEMU is running in -no-shutdown mode, the QEMU process
        may be still alive.
        """
        def _shutdown_by_sendline():
            try:
                session.sendline(self.params.get("shutdown_command"))
                if self.wait_for_shutdown(timeout):
                    return True
            finally:
                session.close()

        if self.params.get("shutdown_command"):
            # Try to destroy with shell command
            LOG.debug("Shutting down VM %s (shell)", self.name)
            try:
                if len(self.virtnet) > 0:
                    session = self.login()
                else:
                    session = self.serial_login()
            except (IndexError) as e:
                try:
                    session = self.serial_login()
                except (remote.LoginError, virt_vm.VMError) as e:
                    LOG.debug(e)
                else:
                    # Successfully get session by serial_login()
                    _shutdown_by_sendline()
            except (remote.LoginError, virt_vm.VMError) as e:
                LOG.debug(e)
            else:
                # There is no exception occurs
                _shutdown_by_sendline()

    def _cleanup(self, free_mac_addresses):
        """
        Do cleanup works
            .removes VM monitor files.
            .process close
            .{serial,virtio}_console close
            .logsessions close
            .delete tmp files
            .free_mac_addresses, if needed
            .delete macvtap, if needed

        :param free_mac_addresses: Whether to release the VM's NICs back
                to the address pool.
        """
        self.monitors = []
        if self.pci_assignable:
            self.pci_assignable.release_devs()
            self.pci_assignable = None
        if self.process:
            self.process.close()
        self.cleanup_serial_console()
        if self.logsessions:
            for key in self.logsessions:
                self.logsessions[key].close()

        # Generate the tmp file which should be deleted.
        file_list = [self.get_testlog_filename()]
        file_list += qemu_monitor.get_monitor_filenames(self)
        file_list += self.get_serial_console_filenames()
        file_list += list(self.logs.values())

        for f in file_list:
            try:
                if f:
                    os.unlink(f)
            except OSError:
                pass

        if hasattr(self, "migration_file"):
            try:
                os.unlink(self.migration_file)
            except OSError:
                pass

        if free_mac_addresses:
            for nic_index in xrange(0, len(self.virtnet)):
                self.free_mac_address(nic_index)

        port_mapping = {}
        for nic in self.virtnet:
            if nic.nettype == 'macvtap':
                tap = utils_net.Macvtap(nic.ifname)
                tap.delete()
            elif nic.ifname:
                port_mapping[nic.ifname] = nic

        if port_mapping:
            queues_num = sum([int(_.queues) for _ in port_mapping.values()])
            deletion_time = max(5, math.ceil(queues_num / 8))
            utils_misc.wait_for(lambda: set(port_mapping.keys()).isdisjoint(
                utils_net.get_net_if()), deletion_time)
            for inactive_port in set(port_mapping.keys()).difference(utils_net.get_net_if()):
                nic = port_mapping.pop(inactive_port)
                self._del_port_from_bridge(nic)
            for active_port in port_mapping.keys():
                LOG.warning("Deleting %s failed during tap cleanup" % active_port)

    def destroy(self, gracefully=True, free_mac_addresses=True):
        """
        Destroy the VM.

        If gracefully is True, first attempt to shutdown the VM with a shell
        command.  Then, attempt to destroy the VM via the monitor with a 'quit'
        command.  If that fails, send SIGKILL to the qemu process.

        :param gracefully: If True, an attempt will be made to end the VM
                using a shell command before trying to end the qemu process
                with a 'quit' or a kill signal.
        :param free_mac_addresses: If True, the MAC addresses used by the VM
                will be freed.
        """
        try:
            # Is it already dead?
            if self.is_dead():
                return

            LOG.debug("Destroying VM %s (PID %s)", self.name,
                      self.get_pid())

            kill_timeout = int(self.params.get("kill_timeout", "60"))

            if gracefully:
                self.graceful_shutdown(kill_timeout)
                if self.is_dead():
                    LOG.debug("VM %s down (shell)", self.name)
                    return
                else:
                    LOG.debug("VM %s failed to go down (shell)", self.name)

            if self.monitor:
                # Try to finish process with a monitor command
                LOG.debug("Ending VM %s process (monitor)", self.name)
                try:
                    self.monitor.quit()
                except Exception as e:
                    LOG.warn(e)
                    if self.is_dead():
                        LOG.warn("VM %s down during try to kill it "
                                 "by monitor", self.name)
                        return
                else:
                    # Wait for the VM to be really dead
                    if self.wait_until_dead(5, 0.5, 0.5):
                        LOG.debug("VM %s down (monitor)", self.name)
                        return
                    else:
                        LOG.debug("VM %s failed to go down (monitor)",
                                  self.name)

            # If the VM isn't dead yet...
            pid = self.process.get_pid()
            LOG.debug("Ending VM %s process (killing PID %s)",
                      self.name, pid)
            try:
                utils_misc.kill_process_tree(pid, 9, timeout=60)
                LOG.debug("VM %s down (process killed)", self.name)
            except RuntimeError:
                # If all else fails, we've got a zombie...
                LOG.error("VM %s (PID %s) is a zombie!", self.name,
                          self.process.get_pid())
        finally:
            self._cleanup(free_mac_addresses)

    @property
    def monitor(self):
        """
        Return the main monitor object, selected by the parameter main_monitor.
        If main_monitor isn't defined or it refers to a nonexistent monitor,
        return the first monitor.
        If no monitors exist, return None.
        """
        for m in self.monitors:
            if m.name == self.params.get("main_monitor"):
                return m
        if self.monitors:
            return self.monitors[0]
        return None

    @property
    def catch_monitor(self):
        """
        Return the catch monitor object, selected by the parameter
        catch_monitor.
        If catch_monitor isn't defined or it refers to a nonexistent monitor,
        return the last monitor.
        If no monitors exist, return None.
        """
        for m in self.monitors:
            if m.name == self.params.get("catch_monitor"):
                return m
        if self.monitors:
            return self.monitors[-1]
        return None

    def get_monitors_by_type(self, mon_type):
        """
        Return list of monitors of mon_type type.
        :param mon_type: desired monitor type (qmp, human)
        """
        return [_ for _ in self.monitors if _.protocol == mon_type]

    def get_peer(self, netid):
        """
        Return the peer of netdev or network device.

        :param netid: id of netdev or device
        :return: id of the peer device otherwise None
        """
        o = self.monitor.info("network")
        network_info = o
        if isinstance(o, dict):
            network_info = o.get["return"]

        netdev_peer_re = self.params.get("netdev_peer_re")
        if not netdev_peer_re:
            default_netdev_peer_re = "\s{2,}(.*?): .*?\\\s(.*?):"
            LOG.warning("Missing config netdev_peer_re for VM %s, "
                        "using default %s", self.name,
                        default_netdev_peer_re)
            netdev_peer_re = default_netdev_peer_re

        pairs = re.findall(netdev_peer_re, network_info, re.S)
        for nic, tap in pairs:
            if nic == netid:
                return tap
            if tap == netid:
                return nic

        return None

    def get_ifname(self, nic_index=0):
        """
        Return the ifname of a bridge/tap device associated with a NIC.

        :param nic_index: Index of the NIC
        """
        return self.virtnet[nic_index].ifname

    def get_pid(self):
        """
        Return the VM's PID.  If the VM is dead return None.

        :note: This works under the assumption that self.process.get_pid()
        :return: the PID of the parent shell process.
        """
        try:
            cmd = "ps --ppid=%d -o pid=" % self.process.get_pid()
            children = process.run(cmd, verbose=False,
                                   ignore_status=True).stdout_text.split()
            return int(children[0])
        except (TypeError, IndexError, ValueError):
            return None

    def get_qemu_threads(self):
        """
        Return the list of qemu SPIDs

        :return: the list of qemu SPIDs
        """
        try:
            return os.listdir("/proc/%d/task" % self.get_pid())
        except Exception:
            return []

    def get_shell_pid(self):
        """
        Return the PID of the parent shell process.

        :note: This works under the assumption that self.process.get_pid()
        :return: the PID of the parent shell process.
        """
        return self.process.get_pid()

    def get_vnc_port(self):
        """
        Return self.vnc_port.
        """

        return self.vnc_port

    def get_vcpu_pids(self, debug=False):
        """
        Return the list of vcpu PIDs

        :return: the list of vcpu PIDs
        """
        if isinstance(self.monitor, qemu_monitor.QMPMonitor):
            try:
                self.monitor.verify_supported_cmd('query-cpus-fast')
                vcpus_info = self.monitor.query('cpus-fast', debug=debug)
                vcpu_pids = [int(vcpu_info.get('thread-id')) for vcpu_info in vcpus_info]
            except qemu_monitor.MonitorNotSupportedCmdError:
                vcpus_info = self.monitor.query('cpus', debug=debug)
                vcpu_pids = [int(vcpu_info.get('thread_id')) for vcpu_info in vcpus_info]
        else:
            vcpus_info = self.monitor.info('cpus', debug=debug).splitlines()
            vcpu_pids = [int(vcpu_info.split('thread_id=')[1]) for vcpu_info in vcpus_info]

        return vcpu_pids

    def _get_hotpluggable_vcpu_qids(self):
        """
        :return: list of hotpluggable vcpu ids
        """
        vcpu_ids_list = []
        out = self.monitor.info("hotpluggable-cpus", debug=False)
        if self.monitor.protocol == "qmp":
            vcpu_ids_list = [vcpu_info["qom-path"].rsplit("/", 1)[-1]
                             for vcpu_info in out if "qom-path" in vcpu_info
                             and "peripheral" in vcpu_info["qom-path"]]
        elif self.monitor.protocol == "human":
            vcpu_ids_list = re.findall(r'qom_path: "/\D+/peripheral/(\S+)"',
                                       out, re.M)
        return vcpu_ids_list

    def get_vhost_threads(self, vhost_thread_pattern):
        """
        Return the list of vhost threads PIDs

        :param vhost_thread_pattern: a regex to match the vhost threads
        :type vhost_thread_pattern: string
        :return: a list of vhost threads PIDs
        :rtype: builtin.list
        """
        return [int(_) for _ in re.findall(vhost_thread_pattern %
                                           self.get_pid(),
                                           process.run("ps aux",
                                                       verbose=False).stdout_text)]

    def get_shared_meminfo(self):
        """
        Returns the VM's shared memory information.

        :return: Shared memory used by VM (MB)
        """
        if self.is_dead():
            LOG.error("Could not get shared memory info from dead VM.")
            return None

        filename = "/proc/%d/statm" % self.get_pid()
        shm = int(open(filename).read().split()[2])
        # statm stores information in pages, translate it to MB
        return shm * 4.0 / 1024

    def get_spice_var(self, spice_var):
        """
        Returns string value of spice variable of choice or None
        :param spice_var - spice related variable 'spice_port', ...
        """
        return self.spice_options.get(spice_var, None)

    def _get_bus(self, params, dtype=None, pcie=False):
        """
        Deal with different buses for multi-arch
        """
        if self.params.get("machine_type").startswith('s390'):
            return self._get_ccw_bus()
        else:
            return self._get_pci_bus(params, dtype, pcie)

    def _get_ccw_bus(self):
        """
        Get device parent bus for s390x
        """
        return {'aobject': 'virtual-css'}

    def _get_pci_bus(self, params, dtype=None, pcie=False):
        """
        Get device parent pci bus by dtype

        :param params: test params for the device
        :param dtype: device type like, 'nic', 'disk',
                      'vio_rng', 'vio_port' or 'cdrom'
        :param pcie: it's a pcie device or not (bool type)

        :return: return bus spec dict
        """
        machine_type = params.get("machine_type", "")
        if "mmio" in machine_type:
            return None
        if dtype and "%s_pci_bus" % dtype in params:
            return {"aobject": params["%s_pci_bus" % dtype]}
        if machine_type == "q35" and not pcie:
            # for legacy pic device(eg. rtl8139, e1000)
            devices = qcontainer.DevContainer(
                    self.qemu_binary,
                    self.name,
                    self.params.get('strict_mode'),
                    self.params.get('workaround_qemu_qmp_crash'),
                    self.params.get('allow_hotplugged_vm'))
            if devices.has_device('pcie-pci-bridge'):
                bridge_type = 'pcie-pci-bridge'
            else:
                bridge_type = 'pci-bridge'
            return {'aobject': '%s-0' % bridge_type}
        return {'aobject': params.get('pci_bus', 'pci.0')}

    @error_context.context_aware
    def hotplug_vcpu(self, cpu_id=None, plug_command="", unplug=""):
        """
        Hotplug/unplug a vcpu, if not assign the cpu_id, will use the minimum
        unused. The function will use the plug_command if you assigned it,
        else the function will use the command automatically generated based
        on the type of monitor

        :param cpu_id  the cpu_id you want hotplug/unplug.
        """
        vcpu_threads_count = len(self.vcpu_threads)
        plug_cpu_id = cpu_id
        if plug_cpu_id is None:
            plug_cpu_id = vcpu_threads_count
        if plug_command:
            # vcpu device based hotplug command for ppc64le looks like
            # device_add CPU_MODEL-spapr-cpu-core,id=core{0},core-id={0}
            # to place the cpu_id multiple places, used format.
            if plug_command.__contains__('{'):
                vcpu_add_cmd = plug_command.format(plug_cpu_id)
            else:
                vcpu_add_cmd = plug_command % plug_cpu_id
        else:
            if self.monitor.protocol == 'human':
                vcpu_add_cmd = "cpu_set %s online" % plug_cpu_id
            elif self.monitor.protocol == 'qmp':
                vcpu_add_cmd = "cpu-add id=%s" % plug_cpu_id

        try:
            self.monitor.verify_supported_cmd(vcpu_add_cmd.split()[0])
        except qemu_monitor.MonitorNotSupportedCmdError:
            raise exceptions.TestSkipError("%s monitor not support cmd '%s'" %
                                           (self.monitor.protocol,
                                            vcpu_add_cmd))
        try:
            # vcpu device based hotplug command contains arguments and with
            # convert=True, arguments will be filtered.
            cmd_output = self.monitor.send_args_cmd(vcpu_add_cmd, convert=False)
        except qemu_monitor.QMPCmdError as e:
            return (False, str(e))

        # Will hotplug/unplug more than one vcpu.
        add_remove_count = int(self.params.get("vcpu_threads", 1))
        if unplug == "yes":
            modified_vcpu_threads = vcpu_threads_count - add_remove_count
        else:
            modified_vcpu_threads = vcpu_threads_count + add_remove_count
        if len(self.vcpu_threads) == modified_vcpu_threads:
            return(True, plug_cpu_id)
        else:
            return(False, cmd_output)

    @error_context.context_aware
    def hotplug_vcpu_device(self, vcpu_id):
        """
        Hotplug a vcpu device and verify that this step is successful.
        :param vcpu_id: the vcpu id you want to hotplug.
        """
        try:
            vcpu_device = self.devices.get_by_qid(vcpu_id)
            if vcpu_device[0].is_enabled():
                raise virt_vm.VMDeviceStateError("%s has been enabled"
                                                 % vcpu_id)
        except IndexError:
            raise virt_vm.VMDeviceNotFoundError("Cannot find vcpu device %s"
                                                % vcpu_id)
        else:
            vcpu_device = vcpu_device[0]

        out, ver_out = vcpu_device.enable(self.monitor)
        if ver_out is False:
            raise virt_vm.VMDeviceCheckError("Failed to hotplug %s: %s"
                                             % (vcpu_id, out))

        vcpu_inserted = vcpu_id in self._get_hotpluggable_vcpu_qids()
        if not vcpu_inserted:
            out = "Could not find %s in hotpluggable CPUs" % vcpu_id
            raise virt_vm.VMDeviceCheckError("Failed to hotplug %s: %s"
                                             % (vcpu_id, out))
        # Workaround to make vm can be migrated after hotplug.
        self.params["vcpu_enable_%s" % vcpu_id] = "yes"

    @error_context.context_aware
    def hotunplug_vcpu_device(self, vcpu_id, verify_timeout=10):
        """
        Hotunplug a vcpu device and verify that this step is successful.
        :param vcpu_id: the vcpu id you want to hotunplug.
        :param verify_timeout: execution timeout
        """
        try:
            vcpu_device = self.devices.get_by_qid(vcpu_id)
            if not vcpu_device[0].is_enabled():
                raise virt_vm.VMDeviceStateError("%s has been disabled"
                                                 % vcpu_id)
        except IndexError:
            raise virt_vm.VMDeviceNotFoundError("Cannot find vcpu device %s"
                                                % vcpu_id)
        else:
            vcpu_device = vcpu_device[0]

        out, ver_out = vcpu_device.disable(self.monitor)
        if ver_out is False:
            raise virt_vm.VMDeviceCheckError("Failed to hotunplug %s: %s"
                                             % (vcpu_id, out))

        if not utils_misc.wait_for(
                lambda: vcpu_id not in self._get_hotpluggable_vcpu_qids(),
                verify_timeout):
            out = "Can still find %s in hotpluggable CPUs" % vcpu_id
            raise virt_vm.VMDeviceCheckError("Failed to hotunplug %s: %s"
                                             % (vcpu_id, out))
        # Workaround to make vm can be migrated after hotunplug.
        self.params["vcpu_enable_%s" % vcpu_id] = "no"

    @error_context.context_aware
    def hotplug_nic(self, **params):
        """
        Convenience method wrapper for add_nic() and add_netdev().

        :return: dict-like object containing nic's details
        """
        nic_name = self.add_nic(**params)["nic_name"]
        self.activate_netdev(nic_name)
        self.activate_nic(nic_name)
        return self.virtnet[nic_name]

    @error_context.context_aware
    def hotunplug_nic(self, nic_index_or_name):
        """
        Convenience method wrapper for del/deactivate nic and netdev.
        """
        # make sure we got a name
        nic_name = self.virtnet[nic_index_or_name].nic_name
        self.deactivate_nic(nic_name)
        self.deactivate_netdev(nic_name)
        self.del_nic(nic_name)

    @error_context.context_aware
    def add_netdev(self, **params):
        """
        Hotplug a netdev device.

        :param params: NIC info. dict.
        :return: netdev_id
        """
        nic_name = params['nic_name']
        nic = self.virtnet[nic_name]
        nic_index = self.virtnet.nic_name_index(nic_name)
        nic.set_if_none('netdev_id', utils_misc.generate_random_id())
        nic.set_if_none('ifname', self.virtnet.generate_ifname(nic_index))
        nic.set_if_none('netdev_extra_params',
                        params.get('netdev_extra_params'))
        nic.set_if_none('nettype', 'bridge')
        if nic.nettype in ['bridge', 'macvtap']:  # implies tap
            # destination is required, hard-code reasonable default if unset
            # nic.set_if_none('netdst', 'virbr0')
            # tapfd allocated/set in activate because requires system resources
            nic.set_if_none('queues', '1')
            ids = []
            for i in range(int(nic.queues)):
                ids.append(utils_misc.generate_random_id())
            nic.set_if_none('tapfd_ids', ids)

        elif nic.nettype == 'user':
            pass  # nothing to do
        else:  # unsupported nettype
            raise virt_vm.VMUnknownNetTypeError(self.name, nic_name,
                                                nic.nettype)
        return nic.netdev_id

    @error_context.context_aware
    def del_netdev(self, nic_index_or_name):
        """
        Remove netdev info. from nic on VM, does not deactivate.

        :param: nic_index_or_name: name or index number for existing NIC
        """
        nic = self.virtnet[nic_index_or_name]
        error_context.context("removing netdev info from nic %s from vm %s" % (
            nic, self.name))
        for propertea in ['netdev_id', 'ifname', 'queues', 'failover',
                          'tapfds', 'tapfd_ids', 'vectors']:
            if propertea in nic:
                del nic[propertea]

    def add_nic(self, **params):
        """
        Add new or setup existing NIC, optionally creating netdev if None

        :param params: Parameters to set
        :param nic_name: Name for existing or new device
        :param nic_model: Model name to emulate
        :param netdev_id: Existing qemu net device ID name, None to create new
        :param mac: Optional MAC address, None to randomly generate.
        """
        # returns existing or new nic object
        if params['nic_model'] == 'virtio':
            machine_type = self.params.get("machine_type")
            if "s390" in machine_type:
                model = "virtio-net-ccw"
            elif '-mmio:' in machine_type:
                model = "virtio-net-device"
            else:
                model = "virtio-net-pci"
            params['nic_model'] = model
        nic = super(VM, self).add_nic(**params)
        nic_index = self.virtnet.nic_name_index(nic.nic_name)
        nic.set_if_none('vlan', str(nic_index))
        nic.set_if_none('device_id', utils_misc.generate_random_id())
        nic.set_if_none('queues', '1')
        if 'netdev_id' not in nic:
            # virtnet items are lists that act like dicts
            nic.netdev_id = self.add_netdev(**dict(nic))
        nic.set_if_none('nic_model', params['nic_model'])
        nic.set_if_none('queues', params.get('queues', '1'))
        if params.get("enable_msix_vectors") == "yes" and int(nic.queues) > 1:
            nic.set_if_none('vectors', 2 * int(nic.queues) + 2)
        return nic

    @error_context.context_aware
    def activate_netdev(self, nic_index_or_name):
        """
        Activate an inactive host-side networking device

        :raise: IndexError if nic doesn't exist
        :raise: VMUnknownNetTypeError: if nettype is unset/unsupported
        :raise: IOError if TAP device node cannot be opened
        :raise: VMAddNetDevError: if operation failed
        """
        nic = self.virtnet[nic_index_or_name]
        netdev_id = nic.netdev_id
        error_context.context("Activating netdev for %s based on %s" %
                              (self.name, nic))
        msg_sfx = ("nic %s on vm %s" % (nic_index_or_name, self.name))

        netdev_args = {}
        if nic.nettype in ['bridge', 'macvtap']:
            net_backend = "tap"
            error_context.context("Opening tap device node for %s " % nic.ifname,
                                  LOG.debug)
            if nic.nettype == "bridge":
                tun_tap_dev = "/dev/net/tun"
                python_tapfds = utils_net.open_tap(tun_tap_dev, nic.ifname,
                                                   queues=nic.queues,
                                                   vnet_hdr=False)
            elif nic.nettype == "macvtap":
                macvtap_mode = self.params.get("macvtap_mode", "vepa")
                o_macvtap = utils_net.create_macvtap(nic.ifname, macvtap_mode,
                                                     nic.netdst, nic.mac)
                tun_tap_dev = o_macvtap.get_device()
                python_tapfds = utils_net.open_macvtap(o_macvtap, nic.queues)

            qemu_fds = "/proc/%s/fd" % self.get_pid()
            openfd_list = os.listdir(qemu_fds)
            for i in range(int(nic.queues)):
                error_context.context("Assigning tap %s to qemu by fd" %
                                      nic.tapfd_ids[i], LOG.info)
                self.monitor.getfd(int(python_tapfds.split(':')[i]),
                                   nic.tapfd_ids[i])
            n_openfd_list = os.listdir(qemu_fds)
            new_fds = list(set(n_openfd_list) - set(openfd_list))

            if not new_fds:
                err_msg = "Can't get the fd that qemu process opened!"
                raise virt_vm.VMAddNetDevError(err_msg)
            qemu_tapfds = [fd for fd in new_fds if os.readlink(
                           os.path.join(qemu_fds, fd)) == tun_tap_dev]
            if not qemu_tapfds or len(qemu_tapfds) != int(nic.queues):
                err_msg = "Can't get the tap fd in qemu process!"
                raise virt_vm.VMAddNetDevError(err_msg)
            nic.set_if_none("tapfds", ":".join(qemu_tapfds))

            if not self.devices:
                err_msg = "Can't add nic for VM which is not running."
                raise virt_vm.VMAddNetDevError(err_msg)
            if ((int(nic.queues)) > 1 and
                    ',fds=' in self.devices.get_help_text()):
                netdev_args["fds"] = nic.tapfds
            else:
                netdev_args["fd"] = nic.tapfds
            error_context.context("Raising interface for " + msg_sfx,
                                  LOG.debug)
            utils_net.bring_up_ifname(nic.ifname)
            # assume this will puke if netdst unset
            if nic.netdst is not None and nic.nettype == "bridge":
                error_context.context("Raising bridge for " + msg_sfx,
                                      LOG.debug)
                utils_net.add_to_bridge(nic.ifname, nic.netdst)
        elif nic.nettype == 'user':
            net_backend = "user"
        else:  # unsupported nettype
            raise virt_vm.VMUnknownNetTypeError(self.name, nic_index_or_name,
                                                nic.nettype)
        if 'netdev_extra_params' in nic and nic.netdev_extra_params:
            for netdev_param in nic.netdev_extra_params.strip(',').split(','):
                arg_k, arg_v = netdev_param.split('=', 1)
                if arg_k in ["vnet_hdr", "vhost", "vhostforce", "restrict",
                             "ipv4", "ipv6"]:
                    arg_v = arg_v in ["on", "yes", "y"]
                elif arg_k in ["sndbuf", "queues", "poll-us", "ipv6-prefixlen"]:
                    arg_v = int(arg_v)
                netdev_args.update({arg_k: arg_v})
        error_context.context("Hotplugging " + msg_sfx, LOG.debug)
        self.monitor.netdev_add(net_backend, netdev_id, **netdev_args)

        network_info = self.monitor.info("network", debug=False)
        if not re.search(r'{}:'.format(netdev_id), network_info):
            LOG.error(network_info)
            # Don't leave resources dangling
            self.deactivate_netdev(nic_index_or_name)
            raise virt_vm.VMAddNetDevError(("Failed to add netdev: %s for " %
                                            netdev_id) + msg_sfx)

    @error_context.context_aware
    def activate_nic(self, nic_index_or_name):
        """
        Activate an VM's inactive NIC device and verify state

        :param nic_index_or_name: name or index number for existing NIC
        """
        error_context.context("Retrieving info for NIC %s on VM %s" % (
                              nic_index_or_name, self.name))
        nic = self.virtnet[nic_index_or_name]
        nic_params = self.params.object_params(nic.nic_name)
        device_id = nic.device_id
        if self.params.get('machine_type') != 'q35':
            pcie = False
        else:
            pcie = nic['nic_model'] not in ['e1000', 'rtl8139']
        bus_spec = self._get_bus(nic_params, 'nic', pcie)
        dev_params = {'id': device_id, "driver": nic.nic_model,
                      "netdev": nic.netdev_id}
        nic_dev = qdevices.QDevice(params=dev_params, parent_bus=(bus_spec,))
        if 'mac' in nic:
            nic_dev.set_param("mac", nic.mac, dynamic=True)
        if nic['nic_model'].startswith("virtio"):
            if int(nic['queues']) > 1:
                nic_dev.set_param("mq", "on")
                if 'vectors' in nic:
                    nic_dev.set_param("vectors", nic.vectors)
        nic_extra_params = nic.get('nic_extra_params')
        if nic_extra_params:
            nic_extra_params = (_.split('=', 1) for _ in
                                nic_extra_params.strip(',').split(','))
            for i in nic_extra_params:
                nic_dev.set_param(i[0], i[1])
        if 'romfile' in nic:
            nic_dev.set_param("romfile", nic.romfile)

        try:
            out, ver_out = self.devices.simple_hotplug(nic_dev, self.monitor)
        except qcontainer.DeviceHotplugError as err:
            out, ver_out = str(err), False
        if not ver_out:
            raise virt_vm.VMAddNicError("Device %s was not plugged into qdev"
                                        "tree: %s" % (device_id, out))

    @error_context.context_aware
    def deactivate_nic(self, nic_index_or_name, wait=20):
        """
        Reverses what activate_nic did

        :param nic_index_or_name: name or index number for existing NIC
        :param wait: Time test will wait for the guest to unplug the device
        """
        nic = self.virtnet[nic_index_or_name]
        device_id = nic.device_id
        error_context.context("Removing nic %s from VM %s" %
                              (nic_index_or_name, self.name))
        nic_dev = self.devices.get_by_qid(device_id)[0]

        try:
            out, ver_out = self.devices.simple_unplug(nic_dev, self.monitor,
                                                      wait)
        except qcontainer.DeviceUnplugError as err:
            out, ver_out = str(err), False
        if not ver_out:
            raise virt_vm.VMDelNicError("Device %s is not unplugged by "
                                        "guest, please check whether the "
                                        "hotplug module was loaded in "
                                        "guest: %s" % (device_id, out))

    @error_context.context_aware
    def deactivate_netdev(self, nic_index_or_name):
        """
        Reverses what activate_netdev() did

        :param: nic_index_or_name: name or index number for existing NIC
        """
        # FIXME: Need to down interface & remove from bridge????
        nic = self.virtnet[nic_index_or_name]
        netdev_id = nic.netdev_id
        error_context.context("removing netdev id %s from vm %s" %
                              (netdev_id, self.name))
        self.monitor.netdev_del(netdev_id)

        network_info = self.monitor.info("network", debug=False)
        if re.search(r'{}:'.format(netdev_id), network_info):
            LOG.error(network_info)
            raise virt_vm.VMDelNetDevError("Fail to remove netdev %s" %
                                           netdev_id)
        if nic.nettype == 'macvtap':
            tap = utils_net.Macvtap(nic.ifname)
            tap.delete()

    @error_context.context_aware
    def del_nic(self, nic_index_or_name):
        """
        Undefine nic parameters, reverses what add_nic did.

        :param nic_index_or_name: name or index number for existing NIC
        :param wait: Time test will wait for the guest to unplug the device
        """
        super(VM, self).del_nic(nic_index_or_name)

    @error_context.context_aware
    def send_fd(self, fd, fd_name="migfd"):
        """
        Send file descriptor over unix socket to VM.

        :param fd: File descriptor.
        :param fd_name: File descriptor identificator in VM.
        """
        error_context.context(
            "Send fd %d like %s to VM %s" %
            (fd, fd_name, self.name))

        LOG.debug("Send file descriptor %s to source VM.", fd_name)
        if self.monitor.protocol == 'human':
            self.monitor.cmd("getfd %s" % (fd_name), fd=fd)
        elif self.monitor.protocol == 'qmp':
            self.monitor.cmd("getfd", args={'fdname': fd_name}, fd=fd)
        error_context.context()

    def mig_finished(self):
        ret = True
        if (self.params["display"] == "spice" and
                self.get_spice_var("spice_seamless_migration") == "on"):
            s = self.monitor.info("spice")
            if isinstance(s, six.string_types):
                ret = len(re.findall("migrated: true", s, re.I)) > 0
            else:
                ret = len(re.findall("true", str(s.get("migrated")), re.I)) > 0
        if ret is False:
            return ret
        o = self.monitor.info("migrate")
        if self._mig_pre_switchover(o):
            self.monitor.migrate_continue('pre-switchover')
            return False
        ret = (self._mig_none(o) or
               self._mig_succeeded(o) or
               self._mig_failed(o) or
               self._mig_cancelled(o))
        return ret

    @staticmethod
    def _is_mig_status(out, expected):
        if isinstance(out, six.string_types):   # HMP
            pattern = "Migration status: %s" % expected
            return pattern in out
        else:                                   # QMP
            return out.get("status") == expected

    def _mig_none(self, out):
        return self._is_mig_status(out, "none")

    def _mig_succeeded(self, out):
        return self._is_mig_status(out, "completed")

    def mig_succeeded(self):
        o = self.monitor.info("migrate")
        return self._mig_succeeded(o)

    def _mig_failed(self, out):
        return self._is_mig_status(out, "failed")

    def mig_failed(self):
        o = self.monitor.info("migrate")
        return self._mig_failed(o)

    def _mig_cancelled(self, out):
        ret = (self._is_mig_status(out, "cancelled") or
               self._is_mig_status(out, "canceled"))
        return ret

    def mig_cancelled(self):
        if self.mig_succeeded():
            raise virt_vm.VMMigrateCancelError(
                "Migration completed successfully")
        elif self.mig_failed():
            raise virt_vm.VMMigrateFailedError("Migration failed")
        o = self.monitor.info("migrate")
        return self._mig_cancelled(o)

    def _mig_pre_switchover(self, out):
        return self._is_mig_status(out, "pre-switchover")

    def mig_pre_switchover(self):
        return self._mig_pre_switchover(self.monitor.info("migrate"))

    def wait_for_migration(self, timeout):
        if not utils_misc.wait_for(self.mig_finished, timeout, 2, 2,
                                   "Waiting for migration to complete"):
            raise virt_vm.VMMigrateTimeoutError("Timeout expired while waiting"
                                                " for migration to finish")

    @error_context.context_aware
    def migrate(self, timeout=virt_vm.BaseVM.MIGRATE_TIMEOUT, protocol="tcp",
                cancel_delay=None, offline=False, stable_check=False,
                clean=True, save_path=data_dir.get_tmp_dir(),
                dest_host="localhost",
                remote_port=None, not_wait_for_migration=False,
                fd_src=None, fd_dst=None, migration_exec_cmd_src=None,
                migration_exec_cmd_dst=None, env=None,
                migrate_capabilities=None, mig_inner_funcs=None,
                migrate_parameters=(None, None)):
        """
        Migrate the VM.

        If the migration is local, the VM object's state is switched with that
        of the destination VM.  Otherwise, the state is switched with that of
        a dead VM (returned by self.clone()).

        :param timeout: Time to wait for migration to complete.
        :param protocol: Migration protocol (as defined in MIGRATION_PROTOS)
        :param cancel_delay: If provided, specifies a time duration after which
                migration will be canceled.  Used for testing migrate_cancel.
        :param offline: If True, pause the source VM before migration.
        :param stable_check: If True, compare the VM's state after migration to
                its state before migration and raise an exception if they
                differ.
        :param clean: If True, delete the saved state files (relevant only if
                stable_check is also True).
        :param save_path: The path for state files.
        :param dest_host: Destination host (defaults to 'localhost').
        :param remote_port: Port to use for remote migration.
        :param not_wait_for_migration: If True migration start but not wait till
                the end of migration.
        :param fd_s: File descriptor for migration to which source
                     VM write data. Descriptor is closed during the migration.
        :param fd_d: File descriptor for migration from which destination
                     VM read data.
        :param migration_exec_cmd_src: Command to embed in '-incoming "exec: "'
                (e.g. 'exec:gzip -c > filename') if migration_mode is 'exec'
                default to listening on a random TCP port
        :param migration_exec_cmd_dst: Command to embed in '-incoming "exec: "'
                (e.g. 'gzip -c -d filename') if migration_mode is 'exec'
                default to listening on a random TCP port
        :param env: Dictionary with test environment
        :param migrate_capabilities: The capabilities for migration to need set.
        :param mig_inner_funcs: Functions to be executed just after the migration is
                started
        :param migrate_parameters: tuple of migration parameters need to be set.
                e.g. for source migrate parameters dict {'x-multifd-channels': 8}
                and  for target migrate parameters dict {'x-multifd-channels': 8}
                migrate_parameters = (source migrate parameters, target migrate parameters).
        """
        def _set_migrate_capability(vm, capability, value, is_src_vm=True):
            state = value == "on"
            vm.monitor.set_migrate_capability(state, capability,
                                              vm.DISABLE_AUTO_X_MIG_OPTS)
            s = vm.monitor.get_migrate_capability(capability,
                                                  vm.DISABLE_AUTO_X_MIG_OPTS)
            if s != state:
                msg = ("Migrate capability '%s' should be '%s', "
                       "but actual result is '%s' on '%s' guest." %
                       (capability, state, s, 'source' if is_src_vm else 'destination'))
                raise exceptions.TestError(msg)

        if protocol not in self.MIGRATION_PROTOS:
            raise virt_vm.VMMigrateProtoUnknownError(protocol)

        error_context.base_context("migrating '%s'" % self.name)

        local = dest_host == "localhost"
        mig_fd_name = None

        if protocol == "fd":
            # Check if descriptors aren't None for local migration.
            if local and (fd_dst is None or fd_src is None):
                (fd_dst, fd_src) = os.pipe()

            mig_fd_name = "migfd_%d_%d" % (fd_src, time.time())
            self.send_fd(fd_src, mig_fd_name)
            os.close(fd_src)

        clone = self.clone()
        if self.params.get('qemu_dst_binary', None) is not None:
            clone.params[
                'qemu_binary'] = utils_misc.get_qemu_dst_binary(self.params)
        if env:
            env.register_vm("%s_clone" % clone.name, clone)

        # "preconfig" is meaningless for dest, remove it whatever the value is
        if "qemu_preconfig" in clone.params:
            del clone.params["qemu_preconfig"]

        try:
            if (local and not (migration_exec_cmd_src and
                               "gzip" in migration_exec_cmd_src)):
                error_context.context("creating destination VM")
                if stable_check:
                    # Pause the dest vm after creation
                    extra_params = clone.params.get("extra_params", "") + " -S"
                    clone.params["extra_params"] = extra_params

                clone.create(migration_mode=protocol, mac_source=self,
                             migration_fd=fd_dst,
                             migration_exec_cmd=migration_exec_cmd_dst)
                if fd_dst:
                    os.close(fd_dst)
                error_context.context()

            if (self.params["display"] == "spice" and local and
                not (protocol == "exec" and
                     (migration_exec_cmd_src and "gzip" in migration_exec_cmd_src))):
                host_ip = utils_net.get_host_ip_address(self.params)
                dest_port = clone.spice_options.get('spice_port', '')
                if self.params.get("spice_ssl") == "yes":
                    dest_tls_port = clone.spice_options.get("spice_tls_port",
                                                            "")
                    cert_s = clone.spice_options.get("spice_x509_server_subj",
                                                     "")
                    cert_subj = "%s" % cert_s[1:]
                    cert_subj += host_ip
                    cert_subj = "\"%s\"" % cert_subj
                else:
                    dest_tls_port = ""
                    cert_subj = ""
                LOG.debug("Informing migration to spice client")
                commands = ["__com.redhat_spice_migrate_info",
                            "spice_migrate_info",
                            "client_migrate_info"]

                cmdline = ""
                for command in commands:
                    try:
                        self.monitor.verify_supported_cmd(command)
                    except qemu_monitor.MonitorNotSupportedCmdError:
                        continue
                    # spice_migrate_info requires host_ip, dest_port
                    # client_migrate_info also requires protocol
                    cmdline = "%s " % (command)
                    if command == "client_migrate_info":
                        cmdline += " protocol=%s," % self.params['display']
                    cmdline += " hostname=%s" % (host_ip)
                    if dest_port:
                        cmdline += ",port=%s" % dest_port
                    if dest_tls_port:
                        cmdline += ",tls-port=%s" % dest_tls_port
                    if cert_subj:
                        cmdline += ",cert-subject=%s" % cert_subj
                    break
                if cmdline:
                    self.monitor.send_args_cmd(cmdline)

            if protocol in ["tcp", "rdma", "x-rdma"]:
                if local:
                    uri = protocol + ":localhost:%d" % clone.migration_port
                else:
                    uri = protocol + ":%s:%d" % (dest_host, remote_port)
            elif protocol == "unix":
                uri = "unix:%s" % clone.migration_file
            elif protocol == "exec":
                if local:
                    if not migration_exec_cmd_src:
                        uri = '"exec:nc localhost %s"' % clone.migration_port
                    else:
                        uri = '"exec:%s"' % (migration_exec_cmd_src)
                else:
                    uri = '"exec:%s"' % (migration_exec_cmd_src)
            elif protocol == "fd":
                uri = "fd:%s" % mig_fd_name

            if offline is True:
                self.monitor.cmd("stop")

            if (local and not (migration_exec_cmd_src and
                               "gzip" in migration_exec_cmd_src)):
                error_context.context("Set migrate capabilities.", LOG.info)
                # XXX: Sync with migration workflow of libvirt by the latest
                # version, since almost no longer use the older version, but
                # will fix it if there are requirements testing still need
                # older version.
                _set_migrate_capability(self, 'pause-before-switchover', 'on', True)
                _set_migrate_capability(clone, 'late-block-activate', 'on', False)

            if migrate_capabilities:
                error_context.context(
                    "Set migrate capabilities.", LOG.info)
                for key, value in list(migrate_capabilities.items()):
                    _set_migrate_capability(self, key, value, True)
                    _set_migrate_capability(clone, key, value, False)

            # source qemu migration parameters dict
            if migrate_parameters[0]:
                LOG.info("Set source migrate parameters before migration: "
                         "%s", str(migrate_parameters[0]))
                for parameter, value in migrate_parameters[0].items():
                    if (parameter == "x-multifd-page-count" and
                            not self.DISABLE_AUTO_X_MIG_OPTS):
                        try:
                            self.monitor.set_migrate_parameter(parameter,
                                                               value, True,
                                                               self.DISABLE_AUTO_X_MIG_OPTS)
                        except qemu_monitor.MonitorNotSupportedError:
                            # x-multifd-page-count was dropped without
                            # replacement, ignore this param
                            LOG.warn("Parameter x-multifd-page-count "
                                     "not supported on src, probably "
                                     "newer qemu, not setting it.")
                            continue
                    else:
                        self.monitor.set_migrate_parameter(parameter, value,
                                                           False,
                                                           self.DISABLE_AUTO_X_MIG_OPTS)
                    s = self.monitor.get_migrate_parameter(parameter,
                                                           self.DISABLE_AUTO_X_MIG_OPTS)
                    if str(s) != str(value):
                        msg = ("Migrate parameter '%s' should be '%s', "
                               "but actual result is '%s' on source guest"
                               % (parameter, value, s))
                        raise exceptions.TestError(msg)

            # target qemu migration parameters dict
            if migrate_parameters[1]:
                LOG.info("Set target migrate parameters before migration: "
                         "%s", str(migrate_parameters[1]))
                # target qemu migration parameters configuration
                for parameter, value in migrate_parameters[1].items():
                    if (parameter == "x-multifd-page-count" and
                            not self.DISABLE_AUTO_X_MIG_OPTS):
                        try:
                            clone.monitor.set_migrate_parameter(parameter,
                                                                value, True,
                                                                False)
                        except qemu_monitor.MonitorNotSupportedError:
                            LOG.warn("Parameter x-multifd-page-count "
                                     "not supported on dst, probably "
                                     "newer qemu, not setting it.")
                            # x-multifd-page-count was dropped without
                            # replacement, ignore this param
                            continue
                    else:
                        clone.monitor.set_migrate_parameter(parameter, value,
                                                            False,
                                                            self.DISABLE_AUTO_X_MIG_OPTS)
                    s = clone.monitor.get_migrate_parameter(parameter,
                                                            self.DISABLE_AUTO_X_MIG_OPTS)
                    if str(s) != str(value):
                        msg = ("Migrate parameter '%s' should be '%s', "
                               "but actual result is '%s' on destination guest"
                               % (parameter, value, s))
                        raise exceptions.TestError(msg)

            LOG.info("Migrating to %s", uri)
            if clone.deferral_incoming:
                _uri = uri
                if protocol == 'tcp':
                    _uri = uri.split(':')
                    _uri = ':[::]:'.join((_uri[0], _uri[-1]))
                clone.monitor.migrate_incoming(_uri)
            self.monitor.migrate(uri)

            if mig_inner_funcs:
                for (func, param) in mig_inner_funcs:
                    if func == "postcopy":
                        # trigger a postcopy at somewhere below the given % of
                        # the 1st pass
                        self.monitor.wait_for_migrate_progress(random.randrange(param))
                        self.monitor.migrate_start_postcopy()
                    elif func == 'continue_pre_switchover':
                        # trigger a continue pre-switchover after the status of
                        # migration is "pre-switchover"
                        if not utils_misc.wait_for(self.mig_pre_switchover,
                                                   timeout=param, first=2, step=1):
                            err = ("Timeout for waiting status of migration "
                                   "to be pre-switchover")
                            raise virt_vm.VMMigrateTimeoutError(err)
                        self.monitor.migrate_continue('pre-switchover')
                    else:
                        msg = ("Unknown migration inner function '%s'" % func)
                        raise exceptions.TestError(msg)

            if not_wait_for_migration:
                return clone

            if cancel_delay:
                error_context.context("Do migrate_cancel after %d seconds" %
                                      cancel_delay, LOG.info)
                time.sleep(cancel_delay)
                self.monitor.cmd("migrate_cancel")
                if not utils_misc.wait_for(self.mig_cancelled, 60, 2, 2,
                                           "Waiting for migration "
                                           "cancellation"):
                    raise virt_vm.VMMigrateCancelError(
                        "Cannot cancel migration")
                return

            self.wait_for_migration(timeout)

            if (local and (migration_exec_cmd_src and
                           "gzip" in migration_exec_cmd_src)):
                error_context.context("creating destination VM")
                if stable_check:
                    # Pause the dest vm after creation
                    extra_params = clone.params.get("extra_params", "") + " -S"
                    clone.params["extra_params"] = extra_params
                clone.create(migration_mode=protocol, mac_source=self,
                             migration_fd=fd_dst,
                             migration_exec_cmd=migration_exec_cmd_dst)

            self.verify_alive()

            # Report migration status
            if self.mig_succeeded():
                LOG.info("Migration completed successfully")
            elif self.mig_failed():
                raise virt_vm.VMMigrateFailedError("Migration failed")
            else:
                raise virt_vm.VMMigrateFailedError("Migration ended with "
                                                   "unknown status")

            error_context.context("after migration")
            if local:
                time.sleep(1)
                self.verify_alive()

            if local and stable_check:
                try:
                    save1 = os.path.join(save_path, "dst-" + clone.instance)
                    save2 = os.path.join(save_path, "src-" + self.instance)
                    clone.save_to_file(save1)
                    self.save_to_file(save2)
                    # Fail if we see deltas
                    md5_save1 = crypto.hash_file(save1)
                    md5_save2 = crypto.hash_file(save2)
                    if md5_save1 != md5_save2:
                        raise virt_vm.VMMigrateStateMismatchError()
                finally:
                    if clean:
                        if os.path.isfile(save1):
                            os.remove(save1)
                        if os.path.isfile(save2):
                            os.remove(save2)

            # Switch self <-> clone
            temp = self.clone(copy_state=True)
            self.destroy(gracefully=False)      # self is the source dead vm
            self.__dict__ = clone.__dict__      # self becomes the dst vm
            clone = temp    # for cleanup purposes keep clone

        finally:
            # If we're doing remote migration and it's completed successfully,
            # self points to a dead VM object
            if not not_wait_for_migration:
                if self.is_alive():
                    # For short period of time the status can be "inmigrate"
                    # for example when using external program
                    # (qemu commit fe823b6f87b2ebedd692ca480ceb9693439d816e)
                    # resume vm during "inmigrate" status can't work, wait until
                    # exit "inmigrate" status and resume vm if needed.
                    if utils_misc.wait_for(lambda: not self.monitor.verify_status('inmigrate'),
                                           timeout=120, step=0.1):
                        if self.is_paused():
                            self.resume()
                    else:
                        raise virt_vm.VMStatusError("vm can't exit 'inmigrate' status"
                                                    "after 120s")
                clone.destroy(gracefully=False)
                if env:
                    env.unregister_vm("%s_clone" % self.name)

    @error_context.context_aware
    def reboot(self, session=None, method="shell", nic_index=0,
               timeout=virt_vm.BaseVM.REBOOT_TIMEOUT, serial=False):
        """
        Reboot the VM and wait for it to come back up by trying to log in until
        timeout expires.

        :param session: A shell session object or None.
        :param method: Reboot method.  Can be "shell" (send a shell reboot
                command) or "system_reset" (send a system_reset monitor command).
        :param nic_index: Index of NIC to access in the VM, when logging in
                after rebooting.
        :param timeout: Time to wait for login to succeed (after rebooting).
        :param serial: Serial login or not (default is False).
        :return: A new shell session object.
        """
        def _go_down(session, timeout):
            try:
                status, output = session.cmd_status_output("tty", timeout=10)
                linux_session = (status == 0) and ("pts" not in output)
                if linux_session:
                    patterns = [r".*[Rr]ebooting.*", r".*[Rr]estarting system.*",
                                r".*[Mm]achine restart.*", r".*Linux version.*"]
                    try:
                        if session.read_until_any_line_matches(
                                patterns, timeout=timeout):
                            return True
                    except Exception:
                        return False
                elif not serial:
                    net_session = self.login(nic_index=nic_index)
                    net_session.close()
                    return False
            except Exception:
                return True

        def _go_down_qmp():
            """
            Listen on QMP monitor for RESET event

            :note: During migration the qemu process finishes, but the
                `monitor.get_event` function is not prepared to treat this
                properly and raises `qemu_monitor.MonitorSocketError`. Let's
                return `False` in such case and keep listening for RESET event
                on the new (dst) monitor.
            :warning: This fails when the source monitor command emits RESET
                event and finishes before we read-it-out. Then we are stuck
                in this loop until a timeout and error is raised.
            """
            try:
                return bool(self.monitor.get_event("RESET"))
            except (qemu_monitor.MonitorSocketError, AttributeError):
                LOG.warn("MonitorSocketError while querying for RESET QMP "
                         "event, it might get lost.")
                return False

        def _shell_reboot(session, timeout):
            if not session:
                if not serial:
                    session = self.wait_for_login(nic_index=nic_index,
                                                  timeout=timeout)
                else:
                    session = self.wait_for_serial_login(timeout=timeout)
            reboot_cmd = self.params.get("reboot_command")
            LOG.debug("Send command: %s" % reboot_cmd)
            session.cmd(reboot_cmd, ignore_all_errors=True)

        error_context.base_context("rebooting '%s'" % self.name, LOG.info)
        error_context.context("before reboot")
        error_context.context()

        start_time = time.time()
        _check_go_down = None
        if (self.params.get("force_reset_go_down_check") == "qmp" and
                isinstance(self.monitor, qemu_monitor.QMPMonitor)):
            _check_go_down = _go_down_qmp
            self.monitor.clear_event("RESET")
        if method == "shell":
            _reboot = partial(_shell_reboot, session, timeout)
            _check_go_down = _check_go_down or partial(_go_down, session, timeout)
        elif method == "system_reset":
            _reboot = self.system_reset
        else:
            raise virt_vm.VMRebootError("Unknown reboot method: %s" % method)
        if _check_go_down is None:
            if isinstance(self.monitor, qemu_monitor.QMPMonitor):
                _check_go_down = _go_down_qmp
                self.monitor.clear_event("RESET")
            else:
                LOG.warning("No suitable way to check for reboot, assuming"
                            " it already rebooted")
                _check_go_down = partial(bool, True)

        try:
            # TODO detect and handle guest crash?
            _reboot()
            error_context.context("waiting for guest to go down", LOG.info)
            if not utils_misc.wait_for(_check_go_down, timeout=timeout):
                raise virt_vm.VMRebootError("Guest refuses to go down")
        finally:
            if session:
                session.close()
        if isinstance(self.monitor, qemu_monitor.QMPMonitor):
            self.monitor.clear_event("RESET")
        shutdown_dur = int(time.time() - start_time)

        error_context.context("logging in after reboot", LOG.info)
        if self.params.get("mac_changeable") == "yes":
            utils_net.update_mac_ip_address(self)

        if serial:
            return self.wait_for_serial_login(timeout=(timeout - shutdown_dur),
                                              status_check=False)
        return self.wait_for_login(nic_index=nic_index,
                                   timeout=(timeout - shutdown_dur),
                                   status_check=False)

    def send_key(self, keystr):
        """
        Send a key event to the VM.

        :param keystr: A key event string (e.g. "ctrl-alt-delete")
        """
        # For compatibility with versions of QEMU that do not recognize all
        # key names: replace keyname with the hex value from the dict, which
        # QEMU will definitely accept
        key_mapping = {"semicolon": "0x27",
                       "comma": "0x33",
                       "dot": "0x34",
                       "slash": "0x35"}
        for key, value in list(key_mapping.items()):
            keystr = keystr.replace(key, value)
        self.monitor.sendkey(keystr)
        time.sleep(0.2)

    # should this really be expected from VMs of all hypervisor types?
    def screendump(self, filename, debug=True):
        try:
            if self.catch_monitor:
                self.catch_monitor.screendump(filename=filename, debug=debug)
        except qemu_monitor.MonitorError as e:
            LOG.warn(e)

    def save_to_file(self, path):
        """
        Override BaseVM save_to_file method
        """
        self.verify_status('paused')  # Throws exception if not
        # Set high speed 1TB/S
        qemu_migration.set_speed(self, str(2 << 39))
        qemu_migration.set_downtime(self, self.MIGRATE_TIMEOUT)
        LOG.debug("Saving VM %s to %s" % (self.name, path))
        # Can only check status if background migration
        self.monitor.migrate("exec:cat>%s" % path, wait=False)
        utils_misc.wait_for(
            # no monitor.migrate-status method
            lambda:
            re.search("(status.*completed)",
                      str(self.monitor.info("migrate")), re.M),
            self.MIGRATE_TIMEOUT, 2, 2,
            "Waiting for save to %s to complete" % path)
        # Restore the speed and downtime to default values
        qemu_migration.set_speed(self, str(32 << 20))
        qemu_migration.monitor.set_downtime(self, 0.03)
        # Base class defines VM must be off after a save
        self.monitor.cmd("system_reset")
        self.verify_status('paused')  # Throws exception if not

    def restore_from_file(self, path):
        """
        Override BaseVM restore_from_file method
        """
        self.verify_status('paused')  # Throws exception if not
        LOG.debug("Restoring VM %s from %s" % (self.name, path))
        # Rely on create() in incoming migration mode to do the 'right thing'
        self.create(name=self.name, params=self.params, root_dir=self.root_dir,
                    timeout=self.MIGRATE_TIMEOUT, migration_mode="exec",
                    migration_exec_cmd="cat " + path, mac_source=self)
        self.resume()

    def savevm(self, tag_name):
        """
        Override BaseVM savevm method
        """
        self.verify_status('paused')  # Throws exception if not
        LOG.debug("Saving VM %s to %s" % (self.name, tag_name))
        self.monitor.send_args_cmd("savevm id=%s" % tag_name)
        self.monitor.cmd("system_reset")
        self.verify_status('paused')  # Throws exception if not

    def loadvm(self, tag_name):
        """
        Override BaseVM loadvm method
        """
        self.verify_status('paused')  # Throws exception if not
        LOG.debug("Loading VM %s from %s" % (self.name, tag_name))
        self.monitor.send_args_cmd("loadvm id=%s" % tag_name)
        self.verify_status('paused')  # Throws exception if not

    def pause(self):
        """
        Pause the VM operation.
        """
        self.monitor.cmd("stop")
        self.verify_status("paused")

    def resume(self, timeout=None):
        """
        Resume the VM operation in case it's stopped.
        """
        self.monitor.cmd("cont")
        if timeout:
            if not self.wait_for_status('running', timeout, step=0.1):
                raise virt_vm.VMStatusError("Failed to enter running status, "
                                            "the actual status is %s" %
                                            self.monitor.get_status())
        else:
            self.verify_status("running")

    def set_link(self, netdev_name, up):
        """
        Set link up/down.

        :param name: Link name
        :param up: Bool value, True=set up this link, False=Set down this link
        """
        self.monitor.set_link(netdev_name, up)

    def get_block_old(self, blocks_info, p_dict={}):
        """
        Get specified block device from monitor's info block command.
        The block device is defined by parameter in p_dict.

        :param p_dict: Dictionary that contains parameters and its value used
                       to define specified block device.

        :param blocks_info: the results of monitor command 'info block'

        :return: Matched block device name, None when not find any device.
        """

        if not p_dict:
            return None

        if isinstance(blocks_info, six.string_types):
            for block in blocks_info.splitlines():
                match = True
                for key, value in six.iteritems(p_dict):
                    if value is True:
                        check_str = "%s=1" % key
                    elif value is False:
                        check_str = "%s=0" % key
                    else:
                        check_str = "%s=%s" % (key, value)
                    if check_str not in block:
                        match = False
                        break
                if match:
                    return block.split(":")[0]
        else:
            # handles QMP output
            def traverse_nested_dict(d):
                iters = [six.iteritems(d)]
                while iters:
                    item = iters.pop()
                    try:
                        k, v = next(item)
                    except StopIteration:
                        continue
                    iters.append(item)
                    if isinstance(v, dict):
                        iters.append(six.iteritems(v))
                    else:
                        yield k, v

            def parse_json(data):
                return json.loads(data[5:])

            def is_json_data(data):
                return isinstance(data, six.string_types) and data.startswith('json:')

            for block in blocks_info:
                matched = True
                for key, value in six.iteritems(p_dict):
                    if is_json_data(value):
                        value = parse_json(value)
                    for (k, v) in traverse_nested_dict(block):
                        if is_json_data(v):
                            v = parse_json(v)
                        if k != key:
                            continue
                        if v != value:
                            matched = False
                        break
                    else:
                        matched = False
                if matched:
                    if self.check_capability(Flags.BLOCKDEV):
                        return block['inserted']['node-name']
                    else:
                        return block['device']
        return None

    def process_info_block(self, blocks_info):
        """
        Process the info block, so that can deal with the new and old
        qemu format.

        :param blocks_info: the output of qemu command
                            'info block'
        """
        block_list = []
        block_entry = []

        if not isinstance(blocks_info, (str, bytes)):
            return block_list

        for block in blocks_info.splitlines():
            if block:
                block_entry.append(block.strip())
            else:
                block_list.append(' '.join(block_entry))
                block_entry = []
        # don't forget the last one
        block_list.append(' '.join(block_entry))
        return block_list

    def get_block(self, p_dict={}):
        """
        Get specified block device from monitor's info block command.
        The block device is defined by parameter in p_dict.

        :param p_dict: Dictionary that contains parameters and its value used
                       to define specified block device.

        :return: Matched block device name, None when not find any device.
        """
        if not p_dict:
            return None

        blocks_info = self.monitor.info("block")
        block = self.get_block_old(blocks_info, p_dict)
        if block:
            return block

        block_list = self.process_info_block(blocks_info)
        for block in block_list:
            for key, value in six.iteritems(p_dict):
                # for new qemu we just deal with key = [removable,
                # file,backing_file], for other types key, we should
                # fixup later
                LOG.info("block = %s" % block)
                if key == 'removable':
                    if value is False:
                        if 'Removable device' not in block:
                            return block.split(":")[0]
                    elif value is True:
                        if 'Removable device' in block:
                            return block.split(":")[0]
                # file in key means both file and backing_file
                if ('file' in key) and (value in block):
                    return block.split(":", 1)[0].split(" ", 1)[0]

        return None

    def check_block_locked(self, value):
        """
        Check whether specified block device is locked or not.
        Return True, if device is locked, else False.

        :param vm: VM object
        :param value: Parameter that can specify block device.
                      Can be any possible identification of a device,
                      Such as device name/image file name/...

        :return: True if device is locked, False if device is unlocked.
        """
        assert value, "Device identification not specified"

        blocks_info = self.monitor.info("block")

        assert value in str(blocks_info), \
            "Device %s not listed in monitor's output" % value

        if isinstance(blocks_info, six.string_types):
            lock_str = "locked=1"
            lock_str_new = "locked"
            no_lock_str = "not locked"
            for block in blocks_info.splitlines():
                if (value in block) and (lock_str in block):
                    return True
            # deal with new qemu
            block_list = self.process_info_block(blocks_info)
            for block_new in block_list:
                if (value in block_new) and ("Removable device" in block_new):
                    if no_lock_str in block_new:
                        return False
                    elif lock_str_new in block_new:
                        return True
        else:
            for block in blocks_info:
                if value in str(block):
                    return block['locked']
        return False

    def live_snapshot(self, base_file, snapshot_file,
                      snapshot_format="qcow2"):
        """
        Take a live disk snapshot.

        :param base_file: base file name
        :param snapshot_file: snapshot file name
        :param snapshot_format: snapshot file format

        :return: File name of disk snapshot.
        """
        device = self.get_block({"file": base_file})

        output = self.monitor.live_snapshot(device, snapshot_file,
                                            format=snapshot_format)
        LOG.debug(output)
        device = self.get_block({"file": snapshot_file})
        if device:
            current_file = device
        else:
            current_file = None

        return current_file

    def block_stream(self, device, speed, base=None, correct=True, **kwargs):
        """
        start to stream block device, aka merge snapshot;

        :param device: device ID;
        :param speed: limited speed, default unit B/s;
        :param base: base file;
        :param correct: auto correct cmd, correct by default
        :param kwargs: optional keyword arguments
        """
        cmd = self.params.get("block_stream_cmd", "block-stream")
        return self.monitor.block_stream(device, speed, base,
                                         cmd, correct=correct, **kwargs)

    def block_commit(self, device, speed, base=None, top=None, correct=True):
        """
        start to commit block device, aka merge snapshot

        :param device: device ID
        :param speed: limited speed, default unit B/s
        :param base: base file
        :param top: top file
        :param correct: auto correct cmd, correct by default
        """
        cmd = self.params.get("block_commit_cmd", "block-commit")
        return self.monitor.block_commit(device, speed, base, top,
                                         cmd, correct=correct)

    def block_mirror(self, device, target, sync,
                     correct=True, **kwargs):
        """
        Mirror block device to target file;

        :param device: device ID
        :param target: destination image file name;
        :param sync: what parts of the disk image should be copied to the
                     destination;
        :param correct: auto correct cmd, correct by default
        :param kwargs: optional keyword arguments including but not limited to below
        :keyword Args:
                format (str): format of target image file
                mode (str): target image create mode, 'absolute-paths' or 'existing'
                speed (int): maximum speed of the streaming job, in bytes per second
                replaces (str): the block driver node name to replace when finished
                granularity (int): granularity of the dirty bitmap, in bytes
                buf_size (int): maximum amount of data in flight from source to target, in bytes
                on-source-error (str): the action to take on an error on the source
                on-target-error (str): the action to take on an error on the target
        """
        cmd = self.params.get("block_mirror_cmd", "drive-mirror")
        return self.monitor.block_mirror(device, target, sync, cmd,
                                         correct=correct, **kwargs)

    def block_reopen(self, device, new_image, format="qcow2", correct=True):
        """
        Reopen a new image, no need to do this step in rhel7 host

        :param device: device ID
        :param new_image: new image filename
        :param format: new image format
        :param correct: auto correct cmd, correct by default
        """
        cmd = self.params.get("block_reopen_cmd", "block-job-complete")
        return self.monitor.block_reopen(device, new_image,
                                         format, cmd, correct=correct)

    def cancel_block_job(self, device, correct=True):
        """
        cancel active job on the image_file

        :param device: device ID
        :param correct: auto correct cmd, correct by default
        """
        cmd = self.params.get("block_job_cancel_cmd", "block-job-cancel")
        return self.monitor.cancel_block_job(device, cmd, correct=correct)

    def pause_block_job(self, device, correct=True):
        """
        Pause an active block streaming operation.
        :param device: device ID
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        cmd = self.params.get("block_job_pause_cmd", "block-job-pause")
        return self.monitor.pause_block_job(device, cmd, correct=correct)

    def resume_block_job(self, device, correct=True):
        """
        Resume a paused block streaming operation.
        :param device: device ID
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        cmd = self.params.get("block_job_resume_cmd", "block-job-resume")
        return self.monitor.resume_block_job(device, cmd, correct=correct)

    def set_job_speed(self, device, speed="0", correct=True):
        """
        set max speed of block job;

        :param device: device ID
        :param speed: max speed of block job
        :param correct: auto correct cmd, correct by default
        """
        cmd = self.params.get("set_block_job_speed", "block-job-set-speed")
        return self.monitor.set_block_job_speed(device, speed,
                                                cmd, correct=correct)

    def get_job_status(self, device):
        """
        get block job info;

        :param device: device ID
        """
        return self.monitor.query_block_job(device)

    def eject_cdrom(self, device, force=False):
        """
        Eject cdrom and open door of the CDROM;

        :param device: device ID;
        :param force: force eject or not;
        """
        if self.check_capability(Flags.BLOCKDEV):
            qdev = self.devices.get_qdev_by_drive(device)
            self.monitor.blockdev_open_tray(qdev, force)
            return self.monitor.blockdev_remove_medium(qdev)
        else:
            return self.monitor.eject_cdrom(device, force)

    def change_media(self, device, target):
        """
        Change media of cdrom;

        :param device: Device ID;
        :param target: new media file;
        """
        if self.check_capability(Flags.BLOCKDEV):
            qdev = self.devices.get_qdev_by_drive(device)
            return self.monitor.blockdev_change_medium(qdev, target)
        else:
            return self.monitor.change_media(device, target)

    def balloon(self, size):
        """
        Balloon memory to given size megat-bytes

        :param size: memory size in mega-bytes
        """
        if isinstance(size, int):
            size = "%s MB" % size
        normalize_data_size = utils_misc.normalize_data_size
        size = int(float(normalize_data_size(size, 'B', '1024')))
        return self.monitor.balloon(size)

    def system_reset(self):
        """ Send system_reset to monitor"""
        return self.monitor.system_reset()
