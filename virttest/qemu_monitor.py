"""
Interfaces to the QEMU monitor.

:copyright: 2008-2010 Red Hat Inc.
"""

from __future__ import division

import logging
import os
import re
import select
import socket
import threading
import time

import six

try:
    import json
except ImportError:
    logging.getLogger('avocado.app').warning(
        "Could not import json module. QMP monitor functionality disabled.")

from . import passfd_setup
from . import utils_misc
from . import cartesian_config
from . import data_dir

from virttest.qemu_capabilities import Flags


LOG = logging.getLogger('avocado.' + __name__)


class MonitorError(Exception):
    pass


class MonitorConnectError(MonitorError):

    def __init__(self, monitor_name):
        MonitorError.__init__(self)
        self.monitor_name = monitor_name

    def __str__(self):
        return "Could not connect to monitor '%s'" % self.monitor_name


class MonitorSocketError(MonitorError):

    def __init__(self, msg, e):
        Exception.__init__(self, msg, e)
        self.msg = msg
        self.e = e

    def __str__(self):
        return "%s    (%s)" % (self.msg, self.e)


class MonitorLockError(MonitorError):
    pass


class MonitorProtocolError(MonitorError):
    pass


class MonitorNotSupportedError(MonitorError):
    pass


class MonitorNotSupportedCmdError(MonitorNotSupportedError):

    def __init__(self, monitor, cmd):
        MonitorError.__init__(self)
        self.monitor = monitor
        self.cmd = cmd

    def __str__(self):
        return ("Not supported cmd '%s' in monitor '%s'" %
                (self.cmd, self.monitor))


class MonitorNotSupportedMigCapError(MonitorNotSupportedError):
    pass


class QMPCmdError(MonitorError):

    def __init__(self, cmd, qmp_args, data):
        MonitorError.__init__(self, cmd, qmp_args, data)
        self.cmd = cmd
        self.qmp_args = qmp_args
        self.data = data

    def __str__(self):
        return ("QMP command %r failed    (arguments: %r,    "
                "error message: %r)" % (self.cmd, self.qmp_args, self.data))


class QMPEventError(MonitorError):

    def __init__(self, cmd, qmp_event, vm_name, name):
        MonitorError.__init__(self, cmd, qmp_event, vm_name, name)
        self.cmd = cmd
        self.qmp_event = qmp_event
        self.name = name
        self.vm_name = vm_name

    def __str__(self):
        return ("QMP event %s not received after %s (monitor '%s.%s')"
                % (self.qmp_event, self.cmd, self.vm_name, self.name))


def get_monitor_filename(vm, monitor_name):
    """
    Return the filename corresponding to a given monitor name.

    :param vm: The VM object which has the monitor.
    :param monitor_name: The monitor name.
    :return: The string of socket file name for qemu monitor.
    """
    return os.path.join(data_dir.get_tmp_dir(),
                        "monitor-%s-%s" % (monitor_name, vm.instance))


def get_monitor_filenames(vm):
    """
    Return a list of all monitor filenames (as specified in the VM's
    params).

    :param vm: The VM object which has the monitors.
    """
    return [get_monitor_filename(vm, m) for m in vm.params.objects("monitors")]


def create_monitor(vm, monitor_name, monitor_params):
    """
    Create monitor object and connect to the monitor socket.

    :param vm: The VM object which has the monitor.
    :param monitor_name: The name of this monitor object.
    :param monitor_params: The dict for creating this monitor object.
    """
    MonitorClass = HumanMonitor
    if monitor_params.get("monitor_type") == "qmp":
        if not utils_misc.qemu_has_option("qmp", vm.qemu_binary):
            # Add a "human" monitor on non-qmp version of qemu.
            LOG.warn("QMP monitor is unsupported by %s,"
                     " creating human monitor instead." % vm.qemu_version)
        else:
            MonitorClass = QMPMonitor

    LOG.info("Connecting to monitor '<%s> %s'", MonitorClass, monitor_name)
    monitor = MonitorClass(vm, monitor_name, monitor_params)
    monitor.verify_responsive()

    return monitor


def wait_for_create_monitor(vm, monitor_name, monitor_params, timeout):
    """
    Wait for the progress of creating monitor object. This function will
    retry to create the Monitor object until timeout.

    :param vm: The VM object which has the monitor.
    :param monitor_name: The name of this monitor object.
    :param monitor_params: The dict for creating this monitor object.
    :param timeout: Time to wait for creating this monitor object.
    """
    # Wait for monitor connection to succeed
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            return create_monitor(vm, monitor_name, monitor_params)
        except MonitorError as e:
            LOG.warn(e)
            time.sleep(1)
    else:
        raise MonitorConnectError(monitor_name)


def get_monitor_function(vm, cmd):
    """
    Get support function by function name
    """
    cmd = vm.monitor.get_workable_cmd(cmd)
    func_name = cmd.replace("-", "_")
    return getattr(vm.monitor, func_name)


def x_non_x_feature(feature):
    """
    Reports the other of the x-/non-x- prefixed feature to the given feature

    :param feature: asked-for feature
    :return: when $feature startswith x- it reports non-x- variant, otherwise
             it prefixes x-
    """
    if feature.startswith("x-"):
        return feature[2:]
    else:
        return "x-%s" % feature


def pick_supported_x_feature(feature, supported_features,
                             disable_auto_x_evaluation,
                             error_on_missing=False, feature_type="Feature"):
    """
    Attempts to choose supported feature with/without "x-" prefix based
    on list of supported features.

    :param feature: feature that allows x- or non-x- prefix
    :param supported_features: list of supported features
    :param error_on_missing: whether to fail when no variant is supported
    :param feature_type: type of the feature used for exception description
    :param disable_auto_x_evaluation: Whether to automatically choose
                                      feature with/without "x-" prefix
    :return: supported variant of the feature or the original one when no
             match is found
    :raise MonitorNotSupportedError: When error_on_missing is enabled and
                                     the feature is not supported.
    """
    if disable_auto_x_evaluation or (feature in supported_features):
        return feature
    feature2 = x_non_x_feature(feature)
    if feature2 in supported_features:
        return feature2
    if error_on_missing:
        raise MonitorNotSupportedError("%s %s, nor %s supported."
                                       % (feature_type, feature, feature2))
    # capability2 also not supported, probably negative testing,
    # return the original capability.
    return feature


class VM(object):
    """
    Dummy class to represent "vm.name" for pickling to avoid circular deps
    """

    def __init__(self, name):
        self.name = name

    def check_capability(self, flag):
        return False

    def get_pid(self):
        return None


class Monitor(object):

    """
    Common code for monitor classes.
    """

    ACQUIRE_LOCK_TIMEOUT = 20
    DATA_AVAILABLE_TIMEOUT = 0
    CONNECT_TIMEOUT = 60

    def __init__(self, vm, name, monitor_params, suppress_exceptions=False):
        """
        Initialize the instance.

        :param vm: The VM which this monitor belongs to.
        :param name: Monitor identifier (a string)
        :param monitor_params: The dict for creating this monitor object.

        :raise MonitorConnectError: Raised if the connection fails
        """
        self.vm = VM(vm.name)
        self._enable_blockdev = vm.check_capability(Flags.BLOCKDEV)
        self.name = name
        self.monitor_params = monitor_params
        self._lock = threading.RLock()
        self._log_lock = threading.RLock()
        self._passfd = None
        self._supported_cmds = []
        self.debug_log = False
        vm_pid = vm.get_pid()
        if vm_pid is None:
            vm_pid = 'unknown'
        self.log_file = "%s-%s-pid-%s.log" % (name, vm.name, vm_pid)
        self.open_log_files = {}
        self._supported_migrate_capabilities = None
        self._supported_migrate_parameters = None

        try:
            backend = monitor_params.get('chardev_backend', 'unix_socket')
            if backend == 'tcp_socket':
                self._socket = socket.socket(
                    socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(self.CONNECT_TIMEOUT)
                host = monitor_params['chardev_host']
                port = int(monitor_params['chardev_port'])
                self._socket.connect((host, port))
            elif backend == 'unix_socket':
                self._socket = socket.socket(
                    socket.AF_UNIX, socket.SOCK_STREAM)
                self._socket.settimeout(self.CONNECT_TIMEOUT)
                file_name = monitor_params.get("monitor_filename")
                self._socket.connect(file_name)
            else:
                raise NotImplementedError("Do not support the chardev backend %s."
                                          % backend)
        except socket.error as details:
            raise MonitorConnectError("Could not connect to monitor socket: %s"
                                      % details)
        self._server_closed = False

    def __del__(self):
        # Automatically close the connection when the instance is garbage
        # collected
        self._close_sock()
        if not self._acquire_lock(lock=self._log_lock):
            raise MonitorLockError("Could not acquire exclusive lock to access"
                                   " %s " % self.open_log_files)
        try:
            del_logs = []
            for log in self.open_log_files:
                self.open_log_files[log].close()
                del_logs.append(log)
            for log in del_logs:
                self.open_log_files.pop(log)
        finally:
            self._log_lock.release()

    # The following two functions are defined to make sure the state is set
    # exclusively by the constructor call as specified in __getinitargs__().
    def __getstate__(self):
        pass

    def __setstate__(self, state):
        pass

    def __getinitargs__(self):
        """
        Unsafe way to allow pickling of this object

        The monitor compounds of several unpickable objects like locks,
        sockets and files. During unpickling this makes the Monitor object
        to re-connect and create new locks, which only works well when
        the original object (pickled one) was already destroyed. If not
        than this new object won't be able to connect to the already opened
        resources and will be crippled. Anyway it's sufficient for our use
        case, but don't tell you were not warned.
        """
        # The Monitor object is usually part of VM. Let's avoid the circular
        # dependency by creating fake VM object which only contains `vm.name`,
        # which is in reality the only information required by Monitor object
        # at this time.
        # Always ignore errors during unpickle as exceptions during "__init__"
        # would cause the whole unpickle operation to fail, leaving us without
        # any representation whatsoever.
        return VM(self.vm.name), self.name, self.monitor_params, True

    def __reduce__(self):
        """
        Backward-compatible way to use __getinitargs__ on py3
        """
        return self.__class__, (self.__getinitargs__())

    def _close_sock(self):
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except socket.error:
            pass
        self._socket.close()

    def _acquire_lock(self, timeout=ACQUIRE_LOCK_TIMEOUT, lock=None):
        end_time = time.time() + timeout
        if not lock:
            lock = self._lock
        while time.time() < end_time:
            if lock.acquire(False):
                return True
            time.sleep(0.05)
        return False

    def _data_available(self, timeout=DATA_AVAILABLE_TIMEOUT):
        if self._server_closed:
            return False
        timeout = max(0, timeout)
        try:
            return bool(select.select([self._socket], [], [], timeout)[0])
        except socket.error as e:
            raise MonitorSocketError("Verifying data on monitor socket", e)

    def _recvall(self):
        """
        Receive bytes from socket.recv().

        return s type: bytes
        """
        s = b""
        while self._data_available():
            try:
                data = self._socket.recv(1024)
            except socket.error as e:
                raise MonitorSocketError("Could not receive data from monitor",
                                         e)
            if not data:
                self._server_closed = True
                break
            s += data
        return s

    def _has_command(self, cmd):
        """
        Check whether kvm monitor support 'cmd'.

        :param cmd: command string which will be checked.

        :return: True if cmd is supported, False if not supported.
        """
        if cmd and cmd in self._supported_cmds:
            return True
        return False

    def _log_command(self, cmd, debug=True, extra_str=""):
        """
        Print log message being sent.

        :param cmd: Command string.
        :param debug: Whether to print the commands.
        :param extra_str: Extra string would be printed in log.
        """
        if self.debug_log or debug:
            LOG.debug("(monitor %s.%s) Sending command '%s' %s",
                      self.vm.name, self.name, cmd, extra_str)

    def _log_lines(self, log_str):
        """
        Record monitor cmd/output in log file.
        """
        if not self._acquire_lock(lock=self._log_lock):
            raise MonitorLockError("Could not acquire exclusive lock to access"
                                   " %s" % self.open_log_files)
        try:
            log_file_dir = utils_misc.get_log_file_dir()
            log = utils_misc.get_path(log_file_dir, self.log_file)
            timestr = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                if log not in self.open_log_files:
                    self.open_log_files[log] = open(log, "a")
                for line in log_str.splitlines():
                    self.open_log_files[log].write(
                        "%s: %s\n" % (timestr, line))
                self.open_log_files[log].flush()
            except Exception as err:
                txt = "Fail to record log to %s.\n" % log
                txt += "Log content: %s\n" % log_str
                txt += "Exception error: %s" % err
                LOG.error(txt)
                self.open_log_files[log].close()
                self.open_log_files.pop(log)
        finally:
            self._log_lock.release()

    @staticmethod
    def _build_args(**kargs):
        """
        Build args used in cmd.
        """
        return {k.replace("_", "-"): v
                for k, v in kargs.items() if v is not None}

    def get_workable_cmd(self, cmd):
        """
        Automatic conversion "-" and "_" in commands if the translate command
        is supported commands;
        """

        def translate(cmd):
            return "-".join(re.split("[_-]", cmd))

        found = False
        if not self._has_command(cmd):
            for _cmd in self._supported_cmds:
                if translate(_cmd) == translate(cmd):
                    found = True
                elif translate(_cmd) == translate("x-%s" % cmd):
                    found = True
                if found:
                    LOG.info("Convert command %s -> %s", cmd, _cmd)
                    return _cmd
        return cmd

    def is_responsive(self):
        """
        Return True if the monitor is responsive.
        """
        if self._socket.fileno() < 0:
            LOG.warning("Monitor socket is already closed")
            return False
        try:
            self.verify_responsive()
            return True
        except MonitorError:
            return False

    def verify_supported_cmd(self, cmd):
        """
        Verify whether cmd is supported by monitor. If not, raise a
        MonitorNotSupportedCmdError Exception.

        :param cmd: The cmd string need to verify.
        """
        if not self._has_command(cmd):
            raise MonitorNotSupportedCmdError(self.name, cmd)

    # Methods that may be implemented by subclasses:

    def human_monitor_cmd(self, cmd="", timeout=None,
                          debug=True, fd=None):
        """
        Send HMP command

        This method allows code to send HMP commands without the need to check
        if the monitor is QMPMonitor or HumanMonitor.

        :param cmd: human monitor command.
        :param timeout: Time duration to wait for response
        :param debug: Whether to print the commands being sent and responses
        :param fd: file object or file descriptor to pass

        :return: The response to the command
        """
        raise NotImplementedError

    # Methods that should work on both classes, as long as human_monitor_cmd()
    # works:
    re_numa_nodes = re.compile(r"^([0-9]+) nodes$", re.M)
    re_numa_node_info = re.compile(r"^node ([0-9]+) (cpus|size): (.*)$", re.M)

    @classmethod
    def parse_info_numa(cls, r):
        """
        Parse 'info numa' output

        See info_numa() for information about the return value.
        """

        nodes = cls.re_numa_nodes.search(r)
        if nodes is None:
            raise Exception(
                "Couldn't get number of nodes from 'info numa' output")
        nodes = int(nodes.group(1))

        data = [[0, set()] for i in range(nodes)]
        for nodenr, field, value in cls.re_numa_node_info.findall(r):
            nodenr = int(nodenr)
            if nodenr > nodes:
                raise Exception(
                    "Invalid node number on 'info numa' output: %d", nodenr)
            if field == 'size':
                if not value.endswith(' MB'):
                    raise Exception("Unexpected size value: %s", value)
                megabytes = int(value[:-3])
                data[nodenr][0] = megabytes
            elif field == 'cpus':
                cpus = set([int(v) for v in value.split()])
                data[nodenr][1] = cpus
        data = [tuple(i) for i in data]
        return data

    def info_numa(self):
        """
        Run 'info numa' command and parse returned information

        :return: An array of (ram, cpus) tuples, where ram is the RAM size in
                 MB and cpus is a set of CPU numbers
        """
        r = self.human_monitor_cmd("info numa")
        r = "\n".join(r.splitlines())
        return self.parse_info_numa(r)

    def info(self, what, debug=True):
        """
        Request info about something and return the response.
        """
        raise NotImplementedError

    def info_block(self, debug=True):
        """
        Request info about blocks and return dict of parsed results
        :return: Dict of disk parameters
        """
        info = self.info('block', debug)
        if isinstance(info, six.string_types):
            try:
                return self._parse_info_block_old(info)
            except ValueError:
                return self._parse_info_block_1_5(info)
        else:
            return self._parse_info_block_qmp(info)

    @staticmethod
    def _parse_info_block_old(info):
        """
        Parse output of "info block" into dict of disk params (qemu < 1.5.0)
        """
        blocks = {}
        info = info.split('\n')
        for line in info:
            if not line.strip():
                continue
            line = line.split(':', 1)
            name = line[0].strip()
            blocks[name] = {}
            if line[1].endswith('[not inserted]'):
                blocks[name]['not-inserted'] = 1
                line[1] = line[1][:-14]
            for _ in line[1].strip().split(' '):
                (prop, value) = _.split('=', 1)
                if value.isdigit():
                    value = int(value)
                blocks[name][prop] = value
        return blocks

    @staticmethod
    def _parse_info_block_1_5(info):
        """
        Parse output of "info block" into dict of disk params (qemu >= 1.5.0)
        """
        blocks = {}
        info = info.split('\n')
        for line in info:
            if not line.strip():
                continue
            if not line.startswith(' '):  # new block device
                line = line.split(':', 1)
                # disregard extra info such as #(blockNNN)
                name = line[0].split(' ', 1)[0]
                line = line[1][1:]
                blocks[name] = {}
                if line == "[not inserted]":
                    blocks[name]['not-inserted'] = 1
                    continue
                line = line.rsplit(' (', 1)
                if len(line) == 1:  # disk_name
                    blocks[name]['file'] = line
                else:  # disk_name (options)
                    blocks[name]['file'] = line[0]
                    options = (_.strip() for _ in line[1][:-1].split(','))
                    _ = False
                    for option in options:
                        if not _:  # First argument is driver (qcow2, raw, ..)
                            blocks[name]['drv'] = option
                            _ = True
                        elif option == 'read-only':
                            blocks[name]['ro'] = 1
                        elif option == 'encrypted':
                            blocks[name]['encrypted'] = 1
                        else:
                            err = ("_parse_info_block_1_5 got option '%s' "
                                   "which is not yet mapped in autotest. "
                                   "Please contact developers on github.com/"
                                   "autotest." % option)
                            raise NotImplementedError(err)
            else:
                try:
                    option, line = line.split(':', 1)
                    option, line = option.strip(), line.strip()
                    if option == "Backing file":
                        line = line.rsplit(' (chain depth: ')
                        blocks[name]['backing_file'] = line[0]
                        blocks[name]['backing_file_depth'] = int(line[1][:-1])
                    elif option == "Removable device":
                        blocks[name]['removable'] = 1
                        if 'not locked' not in line:
                            blocks[name]['locked'] = 1
                        if 'try open' in line:
                            blocks[name]['try-open'] = 1
                except ValueError:
                    continue

        return blocks

    def _parse_info_block_qmp(self, info):
        """
        Parse output of "query block" into dict of disk params
        """
        blocks = {}
        for item in info:
            if not item.get('inserted').get(
                    'node-name') if self._enable_blockdev else not item.get('device'):
                raise ValueError("Incorrect QMP respone, device or node-name "
                                 "not set in info block: %s" % info)
            name = item.get('inserted').get(
                'node-name') if self._enable_blockdev else item.pop('device')
            blocks[name] = {}
            if 'inserted' not in item:
                blocks[name]['not-inserted'] = True
            else:
                for key, value in six.iteritems(item.pop('inserted', {})):
                    blocks[name][key] = value
            for key, value in six.iteritems(item):
                blocks[name][key] = value
        return blocks

    def close(self):
        """
        Close the connection to the monitor and its log file.
        """
        self._close_sock()
        if not self._acquire_lock(lock=self._log_lock):
            raise MonitorLockError("Could not acquire exclusive lock to access"
                                   " %s" % self.open_log_files)
        try:
            del_logs = []
            for log in self.open_log_files:
                self.open_log_files[log].close()
                del_logs.append(log)
            for log in del_logs:
                self.open_log_files.pop(log)
        finally:
            self._log_lock.release()

    def wait_for_migrate_progress(self, target):
        """
        Wait for migration progress to hit a target %
        Note: We exit if we've gone onto another pass rather than wait
        for a target we might never hit.
        """
        old_progress = 0
        while True:
            progress = self.get_migrate_progress()
            if (progress < old_progress or
                    progress >= target):
                break
            # progress < old_progress indicates we must be on
            # another pass (we could also check the sync count)
            old_progress = progress
            time.sleep(0.1)

    def _get_migrate_capability(self, capability,
                                disable_auto_x_evaluation=True):
        """
        Verify the $capability is listed in migrate-capabilities. If not try
        x-/non-x- version. In case none is supported, return the original param

        :param capability: migrate capability
        :param disable_auto_x_evaluation: Whether to automatically choose
                                          feature with/without "x-" prefix
        :return: migrate parameter that is hopefully supported
        """
        return pick_supported_x_feature(capability,
                                        self._supported_migrate_capabilities,
                                        disable_auto_x_evaluation)

    def _get_migrate_parameter(self, parameter, error_on_missing=False,
                               disable_auto_x_evaluation=True):
        """
        Verify the $parameter is listed in migrate-parameters. If not try
        x-/non-x- version. In case none is supported, return the original param

        :param parameter: migrate parameter
        :param disable_auto_x_evaluation: Whether to automatically choose
                                          param with/without "x-" prefix
        :return: migrate parameter that is hopefully supported
        """
        return pick_supported_x_feature(parameter,
                                        self._supported_migrate_parameters,
                                        disable_auto_x_evaluation,
                                        error_on_missing,
                                        "Migration parameter")


class HumanMonitor(Monitor):
    """
    Wraps "human monitor" commands.
    """

    PROMPT_TIMEOUT = 60
    CMD_TIMEOUT = 900

    def __init__(self, vm, name, monitor_params, suppress_exceptions=False):
        """
        Connect to the monitor socket and find the (qemu) prompt.

        :param vm: The VM which this monitor belongs to.
        :param name: Monitor identifier (a string)
        :param monitor_params: The dict for creating this monitor object.

        :raise MonitorConnectError: Raised if the connection fails and
                suppress_exceptions is False
        :raise MonitorProtocolError: Raised if the initial (qemu) prompt isn't
                found and suppress_exceptions is False
        :note: Other exceptions may be raised.  See cmd()'s
                docstring.
        """
        try:
            super(HumanMonitor, self).__init__(vm, name, monitor_params)

            self.protocol = "human"

            # Find the initial (qemu) prompt
            s, o = self._read_up_to_qemu_prompt()
            if not s:
                raise MonitorProtocolError("Could not find (qemu) prompt "
                                           "after connecting to monitor. "
                                           "Output so far: %r" % o)

            self._get_supported_cmds()

        except MonitorError as e:
            self._close_sock()
            if suppress_exceptions:
                LOG.warn(e)
            else:
                raise

    # Private methods
    def _read_up_to_qemu_prompt(self, timeout=PROMPT_TIMEOUT):
        s = b""
        end_time = time.time() + timeout
        while self._data_available(end_time - time.time()):
            data = self._recvall()
            if not data:
                break
            s += data
            try:
                lines = s.decode().splitlines()
                # Sometimes the qemu monitor lacks a line break before the
                # qemu prompt, so we have to be less exigent:
                if lines[-1].split()[-1].endswith("(qemu)"):
                    self._log_lines("\n".join(lines[1:]))
                    return True, "\n".join(lines[:-1])
            except IndexError:
                continue
        s = s.decode(errors="replace")
        if s:
            try:
                self._log_lines(s.splitlines()[1:])
            except IndexError:
                pass
        return False, "\n".join(s.splitlines())

    def _send(self, cmd):
        """
        Send a command without waiting for output.

        :param cmd: Command to send, type: bytes
        :raise MonitorLockError: Raised if the lock cannot be acquired
        :raise MonitorSocketError: Raised if a socket error occurs
        """
        if not self._acquire_lock():
            raise MonitorLockError("Could not acquire exclusive lock to send "
                                   "monitor command '%s'" % cmd)
        try:
            try:
                self._socket.sendall(cmd + b"\n")
                self._log_lines(cmd.decode(errors="replace"))
            except socket.error as e:
                raise MonitorSocketError("Could not send monitor command %r" %
                                         cmd, e)
        finally:
            self._lock.release()

    def _get_supported_cmds(self):
        """
        Get supported human monitor cmds list.
        """
        cmds = self.cmd("help", debug=False)
        if cmds:
            cmd_list = re.findall("^(.*?) ", cmds, re.M)
            self._supported_cmds = [c for c in cmd_list if c]

        if not self._supported_cmds:
            LOG.warn("Could not get supported monitor cmds list")

    def _log_response(self, cmd, resp, debug=True):
        """
        Print log message for monitor cmd's response.

        :param cmd: Command string.
        :param resp: Response from monitor command.
        :param debug: Whether to print the commands.
        """
        if self.debug_log or debug:
            LOG.debug("(monitor %s.%s) Response to '%s'",
                      self.vm.name, self.name, cmd)
            for l in resp.splitlines():
                LOG.debug("(monitor %s.%s)    %s",
                          self.vm.name, self.name, l)

    # Public methods
    def cmd(self, cmd, timeout=CMD_TIMEOUT, debug=True, fd=None):
        """
        Send command to the monitor.

        :param cmd: Command to send to the monitor
        :param timeout: Time duration to wait for the (qemu) prompt to return
        :param debug: Whether to print the commands being sent and responses
        :return: Output received from the monitor
        :raise MonitorLockError: Raised if the lock cannot be acquired
        :raise MonitorSocketError: Raised if a socket error occurs
        :raise MonitorProtocolError: Raised if the (qemu) prompt cannot be
                found after sending the command
        """
        self._log_command(cmd, debug)
        if not self._acquire_lock():
            raise MonitorLockError("Could not acquire exclusive lock to send "
                                   "monitor command '%s'" % cmd)

        try:
            # Read any data that might be available
            self._recvall()
            if fd is not None:
                if self._passfd is None:
                    self._passfd = passfd_setup.import_passfd()
                # If command includes a file descriptor, use passfd module
                self._passfd.sendfd(self._socket, fd, b"%s\n" % cmd.encode())
                self._log_lines(cmd)
            else:
                # Send command
                if debug:
                    LOG.debug("Send command: %s" % cmd)
                self._send(cmd.encode())
            # Read output
            s, o = self._read_up_to_qemu_prompt(timeout)
            # Remove command echo from output
            o = "\n".join(o.splitlines()[1:])
            # Report success/failure
            if s:
                if o:
                    self._log_response(cmd, o, debug)
                return o
            else:
                msg = ("Could not find (qemu) prompt after command '%s'. "
                       "Output so far: %r" % (cmd, o))
                raise MonitorProtocolError(msg)
        finally:
            self._lock.release()

    def human_monitor_cmd(self, cmd="", timeout=CMD_TIMEOUT,
                          debug=True, fd=None):
        """
        Send human monitor command directly

        :param cmd: human monitor command.
        :param timeout: Time duration to wait for response
        :param debug: Whether to print the commands being sent and responses
        :param fd: file object or file descriptor to pass

        :return: The response to the command
        """
        return self.cmd(cmd, timeout, debug, fd)

    def verify_responsive(self):
        """
        Make sure the monitor is responsive by sending a command.
        """
        self.cmd("info status", debug=False)

    def get_status(self):
        return self.cmd("info status", debug=False)

    def verify_status(self, status):
        """
        Verify VM status

        :param status: Optional VM status, 'running' or 'paused'
        :return: return True if VM status is same as we expected
        """
        return (status in self.get_status())

    # Command wrappers
    # Notes:
    # - All of the following commands raise exceptions in a similar manner to
    #   cmd().
    # - A command wrapper should use self._has_command if it requires
    #    information about the monitor's capabilities.
    def send_args_cmd(self, cmdlines, timeout=CMD_TIMEOUT, convert=True):
        """
        Send a command with/without parameters and return its output.
        Have same effect with cmd function.
        Implemented under the same name for both the human and QMP monitors.
        Command with parameters should in following format e.g.:
        'memsave val=0 size=10240 filename=memsave'
        Command without parameter: 'sendkey ctrl-alt-f1'

        :param cmdlines: Commands send to qemu which is separated by ";". For
                         command with parameters command should send in a string
                         with this format:
                         $command $arg_name=$arg_value $arg_name=$arg_value
        :param timeout: Time duration to wait for (qemu) prompt after command
        :param convert: If command need to convert. For commands such as:
                        $command $arg_value
        :return: The output of the command
        :raise MonitorLockError: Raised if the lock cannot be acquired
        :raise MonitorSendError: Raised if the command cannot be sent
        :raise MonitorProtocolError: Raised if the (qemu) prompt cannot be
                found after sending the command
        """
        cmd_output = []
        for cmdline in cmdlines.split(";"):
            if not convert:
                return self.cmd(cmdline, timeout)
            if "=" in cmdline:
                command = cmdline.split()[0]
                cmdargs = " ".join(cmdline.split()[1:]).split(",")
                for arg in cmdargs:
                    value = "=".join(arg.split("=")[1:])
                    if arg.split("=")[0] == "cert-subject":
                        value = value.replace('/', ',')
                    command += " " + value
            else:
                command = cmdline
            cmd_output.append(self.cmd(command, timeout))
        if len(cmd_output) == 1:
            return cmd_output[0]
        return cmd_output

    def quit(self):
        """
        Send "quit" without waiting for output.
        """
        self._send(b"quit")

    def info(self, what, debug=True):
        """
        Request info about something and return the output.
        :param debug: Whether to print the commands being sent and responses
        """
        return self.cmd("info %s" % what, debug=debug)

    def exit_preconfig(self):
        """
        Send "exit_preconfig" and return the response
        """
        return self.cmd(cmd="exit_preconfig")

    def query(self, what):
        """
        Alias for info.
        """
        return self.info(what)

    def screendump(self, filename, debug=True):
        """
        Request a screendump.

        :param filename: Location for the screendump
        :return: The command's output
        """
        return self.cmd(cmd="screendump %s" % filename, debug=debug)

    def system_reset(self):
        """ Reset guest system """
        cmd = "system_reset"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd=cmd)

    def set_link(self, name, up):
        """
        Set link up/down.

        :param name: Link name
        :param up: Bool value, True=set up this link, False=Set down this link
        :return: The response to the command
        """
        status = "on" if up else "off"
        return self.cmd("set_link %s %s" % (name, status))

    def live_snapshot(self, device, snapshot_file, **kwargs):
        """
        Take a live disk snapshot.

        :param device: the name of the device to generate the snapshot from.
        :param snapshot_file: the target of the new image. A new file will be created.
        :param kwargs: optional keyword arguments to pass to func.
        :keyword args (optional):
            format: the format of the snapshot image, default is 'qcow2'.

        :return: The response to the command.
        """
        cmd = "snapshot_blkdev %s %s" % (device, snapshot_file)
        if 'format' in kwargs:
            cmd += " %s" % kwargs['format']
        return self.cmd(cmd)

    def block_stream(self, device, speed=None, base=None,
                     cmd="block_stream", correct=True):
        """
        Start block-stream job;

        :param device: device ID
        :param speed: int type, limited speed(B/s)
        :param base: base file
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        cmd += " %s" % device
        if speed is not None:
            cmd += " %sB" % speed
        if base:
            cmd += " %s" % base
        return self.cmd(cmd)

    def block_commit(self, device, speed=None, base=None, top=None,
                     cmd="block_commit", correct=True):
        """
        Start block-commit job

        :param device: device ID
        :param speed: int type, limited speed(B/s)
        :param base: base file
        :param top: top file
        :param cmd: block commit job command
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        cmd += " %s" % device
        if speed:
            cmd += " %sB" % speed
        if base:
            cmd += " %s" % base
        if top:
            cmd += " %s" % top
        return self.cmd(cmd)

    def set_block_job_speed(self, device, speed=0,
                            cmd="block_job_set_speed", correct=True):
        """
        Set limited speed for running job on the device

        :param device: device ID
        :param speed: int type, limited speed(B/s)
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        cmd += " %s %sB" % (device, speed)
        return self.cmd(cmd)

    def cancel_block_job(self, device, cmd="block_job_cancel", correct=True):
        """
        Cancel running block stream/mirror job on the device

        :param device: device ID
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        cmd += " %s" % device
        return self.send_args_cmd(cmd)

    def pause_block_job(self, device, cmd="block_job_pause", correct=True):
        """
        Pause an active block streaming operation.
        :param device: device ID
        :param cmd: pause block job command
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        cmd += " %s" % device
        return self.send_args_cmd(cmd)

    def resume_block_job(self, device, cmd="block_job_resume", correct=True):
        """
        Resume a paused block streaming operation.
        :param device: device ID
        :param cmd: resume block job command
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        cmd += " %s" % device
        return self.send_args_cmd(cmd)

    def job_dismiss(self, identifier):
        """Dismiss a block job"""
        raise NotImplementedError

    def blockdev_create(self, job_id, options):
        """
        Create block device image file by qemu

        :param kwargs: dictionary containing required parameters
        :return: block job ID
        :rtype: string
        """
        raise NotImplementedError

    def blockdev_backup(self, options):
        """
        Backup block device via QMP command blockdev-backup

        :param kwargs: dictionary containing required parameters
        :return: block job ID
        :rtype: string
        """
        raise NotImplementedError

    def debug_block_dirty_bitmap_sha256(self, node, bitmap):
        """
        get sha256 of bitmap

        :param string node: node name
        :param string bitmap: bitmap name
        """
        raise NotImplementedError

    def x_debug_block_dirty_bitmap_sha256(self, node, bitmap):
        """
        get sha256 of bitmap

        :param string node: node name
        :param string bitmap: bitmap name
        """
        raise NotImplementedError

    def block_dirty_bitmap_merge(self, node, src_bitmaps, dst_bitmap):
        """
        Merge source bitmaps into target bitmap in node

        :param node: device ID or node-name
        :param src_bitmaps: source bitmap list
        :param dst_bitmap: target bitmap name
        """
        raise NotImplementedError

    def x_block_dirty_bitmap_merge(self, node, src_bitmap, dst_bitmap):
        """
        Merge source bitmaps to target bitmap for given node

        :param string node: block device node name
        :parma list src_bitmaps: list of source bitmaps
        :param string dst_bitmap: target bitmap name
        :raise: MonitorNotSupportedCmdError if 'block-dirty-bitmap-mege' and
                'x-block-dirty-bitmap-mege' commands not supported by QMP
                monitor.
        """
        raise NotImplementedError

    def query_named_block_nodes(self):
        """Query named block nodes info"""
        raise NotImplementedError

    def query_block_job(self, device):
        """
        Get block job status on the device

        :param device: device ID

        :return: dict about job info, return empty dict if no active job
        """
        job = dict()
        output = str(self.info("block-jobs"))
        for line in output.split("\n"):
            if "No" in re.match("\w+", output).group(0):
                continue
            if device in line:
                if "Streaming" in re.match("\w+", output).group(0):
                    job["type"] = "stream"
                else:
                    job["type"] = "mirror"
                job["device"] = device
                job["offset"] = int(re.findall("\d+", output)[-3])
                job["len"] = int(re.findall("\d+", output)[-2])
                job["speed"] = int(re.findall("\d+", output)[-1])
                break
        return job

    def query_jobs(self):
        """Query block job info """
        return self.query("jobs")

    def get_backingfile(self, device):
        """
        Return "backing_file" path of the device

        :param device: device ID

        :return: string, backing_file path
        """
        backing_file = None
        block_info = self.query("block")
        try:
            pattern = "%s:.*backing_file=([^\s]*)" % device
            backing_file = re.search(pattern, block_info, re.M).group(1)
        except Exception:
            pass
        return backing_file

    def block_mirror(self, device, target, sync, cmd="drive_mirror",
                     correct=True, **kwargs):
        """
        Start mirror type block device copy job

        :param device: device name to operate on
        :param target: name of new image file
        :param sync: what parts of the disk image should be copied to the
                     destination
        :param cmd: block mirror command
        :param correct: auto correct command, correct by default
        :param kwargs: optional keyword arguments including but not limited to below
        :keyword Args:
            format (str): format of target image file
            mode (str): target image create mode, 'absolute-paths' or 'existing'
            speed (int): maximum speed of the streaming job, in bytes per second

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        args = " %s %s %s" % (device, target, kwargs.get("format", "qcow2"))
        info = str(self.cmd("help %s" % cmd))
        if (kwargs.get("mode", "absolute-paths")
                == "existing") and "-n" in info:
            args = "-n %s" % args
        if (sync == "full") and "-f" in info:
            args = "-f %s" % args
        if "speed" in info:
            args = "%s %s" % (args, kwargs.get("speed", ""))
        cmd = "%s %s" % (cmd, args)
        return self.cmd(cmd)

    def block_reopen(self, device, new_image_file, image_format,
                     cmd="block_job_complete", correct=True):
        """
        Reopen new target image

        :param device: device ID
        :param new_image_file: new image file name
        :param image_format: new image file format
        :param cmd: image reopen command
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        args = "%s" % device
        info = str(self.cmd("help %s" % cmd))
        if "format" in info:
            args += " %s %s" % (new_image_file, image_format)
        cmd = "%s %s" % (cmd, args)
        return self.cmd(cmd)

    def migrate(self, uri, full_copy=False,
                incremental_copy=False, wait=False):
        """
        Migrate.

        :param uri: destination URI
        :param full_copy: If true, migrate with full disk copy
        :param incremental_copy: If true, migrate with incremental disk copy
        :param wait: If true, wait for completion
        :return: The command's output
        """
        cmd = "migrate"
        if not wait:
            cmd += " -d"
        if full_copy:
            cmd += " -b"
        if incremental_copy:
            cmd += " -i"
        cmd += " %s" % uri
        return self.cmd(cmd)

    def migrate_continue(self, state):
        """
        Continue migration when it's in a paused state.

        :param state: The state the migration is currently expected to be in.
        :return: The command's output.
        """
        return self.cmd("migrate_continue %s" % state)

    def migrate_set_speed(self, value):
        """
        Set maximum speed (in bytes/sec) for migrations.

        :param value: Speed in bytes/sec
        :return: The command's output
        """
        return self.cmd("migrate_set_speed %s" % value)

    def migrate_incoming(self, uri):
        """
        Start an incoming migration, the qemu must have been started
        with -incoming defer.

        :param uri: The Uniform Resource Identifier identifying the
                    source or address to listen on.
        :type uri: str
        """
        return self.cmd("migrate_incoming %s" % uri)

    def migrate_set_downtime(self, value):
        """
        Set maximum tolerated downtime (in seconds) for migration.

        :param value: maximum downtime (in seconds)
        :return: The command's output
        """
        return self.cmd("migrate_set_downtime %s" % value)

    def sendkey(self, keystr, hold_time=1):
        """
        Send key combination to VM.

        :param keystr: Key combination string
        :param hold_time: Hold time in ms (should normally stay 1 ms)
        :return: The command's output
        """
        return self.cmd("sendkey %s %s" % (keystr, hold_time))

    def mouse_move(self, dx, dy):
        """
        Move mouse.

        :param dx: X amount
        :param dy: Y amount
        :return: The command's output
        """
        return self.cmd("mouse_move %s %s" % (dx, dy))

    def mouse_button(self, state):
        """
        Set mouse button state.

        :param state: Button state (1=L, 2=M, 4=R)
        :return: The command's output
        """
        return self.cmd("mouse_button %s" % state)

    def getfd(self, fd, name):
        """
        Receives a file descriptor

        :param fd: File descriptor to pass to QEMU
        :param name: File descriptor name (internal to QEMU)
        :return: The command's output
        """
        return self.cmd("getfd %s" % name, fd=fd)

    def closefd(self, fd, name):
        """
        Close a file descriptor

        :param fd: File descriptor to pass to QEMU
        :param name: File descriptor name (internal to QEMU)
        :return: The command's output
        """
        return self.cmd("closefd %s" % name, fd=fd)

    def system_wakeup(self):
        """
        Wakeup suspended guest.
        """
        cmd = "system_wakeup"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd)

    def nmi(self):
        """
        Inject a NMI on all guest's CPUs.
        """
        return self.cmd("nmi")

    def block_resize(self, device, size):
        """
        Resize the block device size

        :param device: Block device name
        :param size: Block device size need to set to. To keep the same with
                     qmp monitor will use bytes as unit for the block size
        :return: Command output
        """
        size = int(size) // 1024 // 1024
        cmd = "block_resize device=%s,size=%s" % (device, size)
        return self.send_args_cmd(cmd)

    def eject_cdrom(self, device, force=False):
        """
        Eject media of cdrom and open cdrom door;
        """
        cmd = "eject"
        self.verify_supported_cmd(cmd)
        if force:
            cmd += " -f "
        cmd += " %s" % device
        return self.cmd(cmd)

    def change_media(self, device, target):
        """
        Change media of cdrom of drive;
        """
        cmd = "change"
        self.verify_supported_cmd(cmd)
        cmd += " %s %s" % (device, target)
        return self.cmd(cmd)

    def balloon(self, size):
        """
        Balloon VM memory to given size bytes;

        :param size: int type size value.
        """
        self.verify_supported_cmd("balloon")
        normalize_data_size = utils_misc.normalize_data_size
        size = float(normalize_data_size("%sB" % size, 'M', '1024'))
        return self.cmd("balloon %d" % size)

    def _get_migrate_capability(self, capability,
                                disable_auto_x_evaluation=True):
        if self._supported_migrate_capabilities is None:
            ret = self.query("migrate_capabilities")
            caps = []
            for line in ret.splitlines():
                split = line.split(':', 1)
                if len(split) == 2:
                    caps.append(split[0])
            self._supported_migrate_capabilities = caps
        return super(HumanMonitor, self)._get_migrate_capability(capability,
                                                                 disable_auto_x_evaluation)

    def set_migrate_capability(self, state, capability,
                               disable_auto_x_evaluation=True):
        """
        Set the capability of migrate to state.

        :param state: Bool value of capability.
        :param capability: capability which need to set.
        :param disable_auto_x_evaluation: Whether to automatically choose
                                          feature with/without "x-" prefix
        :raise MonitorNotSupportedMigCapError: if the capability is unknown
        """
        cmd = "migrate_set_capability"
        self.verify_supported_cmd(cmd)
        value = "off"
        if state:
            value = "on"
        capability = self._get_migrate_capability(capability,
                                                  disable_auto_x_evaluation)
        cmd += " %s %s" % (capability, value)
        result = self.cmd(cmd)
        if result != "":
            raise MonitorNotSupportedMigCapError("Failed to set capability"
                                                 "%s: %s" %
                                                 (capability, result))
        return result

    def get_migrate_capability(self, capability,
                               disable_auto_x_evaluation=True):
        """
        Get the state of migrate-capability.

        :param capability: capability which need to get.
        :param disable_auto_x_evaluation: Whether to automatically choose
                                          feature with/without "x-" prefix
        :raise MonitorNotSupportedMigCapError: if the capability is unknown
        :return: the state of migrate-capability.
        """
        capability_info = self.query("migrate_capabilities")
        capability = self._get_migrate_capability(capability,
                                                  disable_auto_x_evaluation)
        pattern = r"%s:\s+(on|off)" % capability
        match = re.search(pattern, capability_info, re.M)
        if match is None:
            raise MonitorNotSupportedMigCapError("Unknown capability %s" %
                                                 capability)
        value = match.group(1)
        return value == "on"

    def set_migrate_cache_size(self, value):
        """
        Set the cache size of migrate to value.

        :param value: the cache size to set.
        """
        cmd = "migrate_set_cache_size"
        self.verify_supported_cmd(cmd)
        cmd += " %s" % value
        return self.cmd(cmd)

    def get_migrate_cache_size(self):
        """
        Get the xbzrel cache size. e.g. xbzrel cache size: 1048576 kbytes
        """
        cache_size_info = self.query("migrate_cache_size")
        value = cache_size_info.split(":")[1].split()[0].strip()
        return value

    def _get_migrate_parameter(self, parameter, error_on_missing=False,
                               disable_auto_x_evaluation=True):
        if self._supported_migrate_parameters is None:
            params = []
            for line in self.query("migrate_parameters").splitlines():
                split = line.split(':', 1)
                if len(split) == 2:
                    params.append(split[0])
            self._supported_migrate_parameters = params
        return super(HumanMonitor, self)._get_migrate_parameter(
            parameter, error_on_missing, disable_auto_x_evaluation)

    def set_migrate_parameter(self, parameter, value, error_on_missing=False,
                              disable_auto_x_evaluation=True):
        """
        Set parameters of migrate.

        :param parameter: the parameter which need to set
        :param value: the value of parameter
        :param disable_auto_x_evaluation: Whether to automatically choose
                                          parameter with/without "x-" prefix
        """
        cmd = "migrate_set_parameter"
        self.verify_supported_cmd(cmd)
        parameter = self._get_migrate_parameter(parameter, error_on_missing,
                                                disable_auto_x_evaluation)
        cmd += " %s %s" % (parameter, value)
        return self.cmd(cmd)

    def get_migrate_parameter(self, parameter, disable_auto_x_evaluation=True):
        """
        Get the parameter value. e.g. cpu-throttle-initial: 30

        :param parameter: the parameter which need to get
        :param disable_auto_x_evaluation: Whether to automatically choose
                                          param with/without "x-" prefix
        """
        parameter = self._get_migrate_parameter(parameter,
                                                disable_auto_x_evaluation=disable_auto_x_evaluation)
        for line in self.query("migrate_parameters").splitlines():
            split = line.split(':', 1)
            if split[0] == parameter:
                return split[1].lstrip()

    def migrate_start_postcopy(self):
        """
        Switch into postcopy migrate mode
        """

        return self.cmd("migrate_start_postcopy")

    def get_migrate_progress(self):
        """
        Return the transfered / remaining ram ratio

        :return: percentage remaining for RAM transfer
        """
        status = self.info("migrate", debug=False)
        rem = re.search(r"remaining ram: (\d+) kbytes", status)
        total = re.search(r"total ram: (\d+) kbytes", status)
        if rem and total:
            ret = 100 - 100 * int(rem.group(1)) / int(total.group(1))
            LOG.debug("Migration progress: %s%%", ret)
            return ret
        if "Migration status: completed" in status:
            LOG.debug("Migration progress: 100%")
            return 100
        elif "Migration status: setup" in status:
            LOG.debug("Migration progress: 0%")
            return 0
        raise MonitorError("Unable to parse migration progress:\n%s" % status)

    def system_powerdown(self):
        """
        Requests that a guest perform a powerdown operation.
        """
        cmd = "system_powerdown"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd)

    def netdev_add(self, backend, name, **kwargs):
        """
        Add a network backend.

        :param backend: Type of network backend.
        :param name: Netdev ID.
        """
        kwargs = self._build_args(**kwargs)
        extra_args = "".join([",%s=%s" % (k, v if not isinstance(v, bool) else
                                          "on" if v else "off") for k, v in kwargs.items()])
        netdev_cmd = "netdev_add type=%s,id=%s%s" % (backend, name, extra_args)
        return self.cmd(netdev_cmd)

    def netdev_del(self, name):
        """
        Remove a network backend.

        :param name: Netdev ID
        """
        netdev_cmd = "netdev_del %s" % name
        return self.cmd(netdev_cmd)


class QMPMonitor(Monitor):
    """
    Wraps QMP monitor commands.
    """

    READ_OBJECTS_TIMEOUT = 10
    CMD_TIMEOUT = 900
    RESPONSE_TIMEOUT = 600
    PROMPT_TIMEOUT = 90

    def __init__(self, vm, name, monitor_params, suppress_exceptions=False):
        """
        Connect to the monitor socket, read the greeting message and issue the
        qmp_capabilities command.  Also make sure the json module is available.

        :param vm: The VM which this monitor belongs to.
        :param name: Monitor identifier (a string)
        :param monitor_params: The dict for creating this monitor object.

        :raise MonitorConnectError: Raised if the connection fails and
                suppress_exceptions is False
        :raise MonitorProtocolError: Raised if the no QMP greeting message is
                received and suppress_exceptions is False
        :raise MonitorNotSupportedError: Raised if json isn't available and
                suppress_exceptions is False
        :note: Other exceptions may be raised if the qmp_capabilities command
                fails.  See cmd()'s docstring.
        """
        try:
            super(QMPMonitor, self).__init__(vm, name, monitor_params)

            self.protocol = "qmp"
            self._greeting = None
            self._events = []
            self._supported_hmp_cmds = []

            # Make sure json is available
            try:
                json
            except NameError:
                raise MonitorNotSupportedError("QMP requires the json module "
                                               "(Python 2.6 and up)")

            # Read greeting message
            end_time = time.time() + 20
            output_str = ""
            while time.time() < end_time:
                for obj in self._read_objects():
                    output_str += str(obj)
                    if "QMP" in obj:
                        self._greeting = obj
                        break
                if self._greeting:
                    break
                time.sleep(0.1)
            else:
                raise MonitorProtocolError("No QMP greeting message received."
                                           " Output so far: %s" % output_str)

            # Issue qmp_capabilities
            self.cmd("qmp_capabilities")

            self._get_supported_cmds()

        except MonitorError as e:
            self._close_sock()
            if suppress_exceptions:
                LOG.warn(e)
            else:
                raise

    # Private methods
    def _build_cmd(self, cmd, args=None, q_id=None):
        obj = {"execute": cmd}
        if args is not None:
            obj["arguments"] = args
        if q_id is not None:
            obj["id"] = q_id
        return obj

    def _read_objects(self, timeout=READ_OBJECTS_TIMEOUT):
        """
        Read bytes lines from the monitor and try to "decode" them.
        Stop when all available lines have been successfully decoded, or when
        timeout expires.  If any decoded objects are asynchronous events, store
        them in self._events.  Return all decoded objects.

        :param timeout: Time to wait for all lines to decode successfully
        :return: A list of objects
        """
        if not self._data_available():
            return []
        s = b""
        end_time = time.time() + timeout
        while self._data_available(end_time - time.time()):
            s += self._recvall()
            # Make sure all lines are decodable
            for line in s.splitlines():
                if line:
                    try:
                        json.loads(line)
                    except Exception:
                        # Found an incomplete or broken line -- keep reading
                        break
            else:
                # All lines are OK -- stop reading
                break
        # Decode all decodable lines
        objs = []
        for line in s.splitlines():
            try:
                objs += [json.loads(line)]
                self._log_lines(line.decode(errors="replace"))
            except Exception:
                pass
        # Keep track of asynchronous events
        self._events += [obj for obj in objs if "event" in obj]
        return objs

    def _send(self, data):
        """
        Send raw bytes data without waiting for response.

        :param data: Data to send type: bytes
        :raise MonitorSocketError: Raised if a socket error occurs
        """
        try:
            self._socket.sendall(data)
            self._log_lines(data.decode(errors="replace"))
        except socket.error as e:
            raise MonitorSocketError("Could not send data: %r" % data, e)

    def _get_response(self, q_id=None, timeout=RESPONSE_TIMEOUT):
        """
        Read a response from the QMP monitor.

        :param id: If not None, look for a response with this id
        :param timeout: Time duration to wait for response
        :return: The response dict, or None if none was found
        """
        end_time = time.time() + timeout
        while self._data_available(end_time - time.time()):
            for obj in self._read_objects():
                if isinstance(obj, dict):
                    if q_id is not None and obj.get("id") != q_id:
                        continue
                    if "return" in obj or "error" in obj:
                        return obj

    def _get_supported_cmds(self):
        """
        Get supported qmp cmds list.
        """
        cmds = self.cmd("query-commands", debug=False)
        if cmds:
            self._supported_cmds = [n["name"] for n in cmds if
                                    "name" in n]

        if not self._supported_cmds:
            LOG.warn("Could not get supported monitor cmds list")

    def _get_supported_hmp_cmds(self):
        """
        Get supported human monitor cmds list.
        """
        cmds = self.human_monitor_cmd("help", debug=False)
        if cmds:
            cmd_list = re.findall(
                r"(?:^\w+\|(\w+)\s)|(?:^(\w+?)\s)", cmds, re.M)
            self._supported_hmp_cmds = [(i + j) for i, j in cmd_list if i or j]

        if not self._supported_cmds:
            LOG.warn("Could not get supported monitor cmds list")

    def _has_hmp_command(self, cmd):
        """
        Check whether monitor support hmp 'cmd'.

        :param cmd: command string which will be checked.

        :return: True if cmd is supported, False if not supported.
        """
        if not self._supported_hmp_cmds:
            self._get_supported_hmp_cmds()
        if cmd and cmd in self._supported_hmp_cmds:
            return True
        return False

    def verify_supported_hmp_cmd(self, cmd):
        """
        Verify whether cmd is supported by hmp monitor.
        If not, raise a MonitorNotSupportedCmdError Exception.

        :param cmd: The cmd string need to verify.
        """
        if not self._has_hmp_command(cmd):
            raise MonitorNotSupportedCmdError(self.name, cmd)

    def _log_response(self, cmd, resp, debug=True):
        """
        Print log message for monitor cmd's response.

        :param cmd: Command string.
        :param resp: Response from monitor command.
        :param debug: Whether to print the commands.
        """

        def _log_output(o, indent=0):
            LOG.debug("(monitor %s.%s)    %s%s",
                      self.vm.name, self.name, " " * indent, o)

        def _dump_list(li, indent=0):
            for l in li:
                if isinstance(l, dict):
                    _dump_dict(l, indent + 2)
                else:
                    _log_output(str(l), indent)

        def _dump_dict(di, indent=0):
            for k, v in six.iteritems(di):
                o = "%s%s: " % (" " * indent, k)
                if isinstance(v, dict):
                    _log_output(o, indent)
                    _dump_dict(v, indent + 2)
                elif isinstance(v, list):
                    _log_output(o, indent)
                    _dump_list(v, indent + 2)
                else:
                    o += str(v)
                    _log_output(o, indent)

        if self.debug_log or debug:
            LOG.debug("(monitor %s.%s) Response to '%s' "
                      "(re-formatted)", self.vm.name, self.name, cmd)
            if isinstance(resp, dict):
                _dump_dict(resp)
            elif isinstance(resp, list):
                _dump_list(resp)
            else:
                for l in str(resp).splitlines():
                    _log_output(l)

    # Public methods
    def cmd(self, cmd, args=None, timeout=CMD_TIMEOUT, debug=True, fd=None):
        """
        Send a QMP monitor command and return the response.

        Note: an id is automatically assigned to the command and the response
        is checked for the presence of the same id.

        :param cmd: Command to send, type: string
        :param args: A dict containing command arguments, or None
        :param timeout: Time duration to wait for response
        :param debug: Whether to print the commands being sent and responses
        :param fd: file object or file descriptor to pass

        :return: The response received

        :raise MonitorLockError: Raised if the lock cannot be acquired
        :raise MonitorSocketError: Raised if a socket error occurs
        :raise MonitorProtocolError: Raised if no response is received
        :raise QMPCmdError: Raised if the response is an error message
                            (the exception's args are (cmd, args, data)
                            where data is the error data)
        """
        self._log_command(cmd, debug)
        if not self._acquire_lock():
            raise MonitorLockError("Could not acquire exclusive lock to send "
                                   "QMP command '%s'" % cmd)

        try:
            # Read any data that might be available
            self._read_objects()
            # Send command
            q_id = utils_misc.generate_random_string(8)
            cmdobj = self._build_cmd(cmd, args, q_id)
            if debug:
                LOG.debug("Send command: %s" % cmdobj)
            if fd is not None:
                if self._passfd is None:
                    self._passfd = passfd_setup.import_passfd()
                # If command includes a file descriptor, use passfd module
                self._passfd.sendfd(
                    self._socket, fd, json.dumps(cmdobj).encode() + b"\n")
                self._log_lines(str(cmdobj))
            else:
                self._send(json.dumps(cmdobj).encode() + b"\n")
            # Read response
            r = self._get_response(q_id, timeout)
            if r is None:
                raise MonitorProtocolError("Received no response to QMP "
                                           "command '%s', or received a "
                                           "response with an incorrect id"
                                           % cmd)
            if "return" in r:
                ret = r["return"]
                if ret:
                    self._log_response(cmd, ret, debug)
                return ret
            if "error" in r:
                raise QMPCmdError(cmd, args, r["error"])

        finally:
            self._lock.release()

    def cmd_raw(self, data, timeout=CMD_TIMEOUT):
        """
        Send a raw string to the QMP monitor and return the response.
        Unlike cmd(), return the raw response dict without performing any
        checks on it.

        :param data: The data to send type: string
        :param timeout: Time duration to wait for response
        :return: The response received
        :raise MonitorLockError: Raised if the lock cannot be acquired
        :raise MonitorSocketError: Raised if a socket error occurs
        :raise MonitorProtocolError: Raised if no response is received
        """
        if not self._acquire_lock():
            raise MonitorLockError("Could not acquire exclusive lock to send "
                                   "data: %r" % data)

        try:
            self._read_objects()
            self._send(data.encode())
            r = self._get_response(None, timeout)
            if r is None:
                raise MonitorProtocolError("Received no response to data: %r" %
                                           data)
            return r

        finally:
            self._lock.release()

    def cmd_obj(self, obj, timeout=CMD_TIMEOUT):
        """
        Transform a Python object to JSON, send the resulting string to the QMP
        monitor, and return the response.
        Unlike cmd(), return the raw response dict without performing any
        checks on it.

        :param obj: The object to send
        :param timeout: Time duration to wait for response
        :return: The response received
        :raise MonitorLockError: Raised if the lock cannot be acquired
        :raise MonitorSocketError: Raised if a socket error occurs
        :raise MonitorProtocolError: Raised if no response is received
        """
        return self.cmd_raw(json.dumps(obj) + "\n", timeout)

    def cmd_qmp(self, cmd, args=None, q_id=None, timeout=CMD_TIMEOUT):
        """
        Build a QMP command from the passed arguments, send it to the monitor
        and return the response.
        Unlike cmd(), return the raw response dict without performing any
        checks on it.

        :param cmd: Command to send
        :param args: A dict containing command arguments, or None
        :param id:  An id for the command, or None
        :param timeout: Time duration to wait for response
        :return: The response received
        :raise MonitorLockError: Raised if the lock cannot be acquired
        :raise MonitorSocketError: Raised if a socket error occurs
        :raise MonitorProtocolError: Raised if no response is received
        """
        return self.cmd_obj(self._build_cmd(cmd, args, q_id), timeout)

    def verify_responsive(self):
        """
        Make sure the monitor is responsive by sending a command.
        """
        self.cmd(cmd="query-status", debug=False)

    def get_status(self):
        """
        Get VM status.

        :return: return VM status
        """
        return self.cmd(cmd="query-status", debug=False)

    def verify_status(self, status):
        """
        Verify VM status

        :param status: Optional VM status, 'running' or 'paused'
        :return: return True if VM status is same as we expected
        """
        o = dict(self.cmd(cmd="query-status", debug=False))
        if status == 'paused':
            return (o['running'] is False)
        if status == 'running':
            return (o['running'] is True)
        if o['status'] == status:
            return True
        return False

    def exit_preconfig(self):
        """
        Send "(x-)exit-preconfig" and return the response
        """
        feature = pick_supported_x_feature("exit-preconfig",
                                           self._supported_cmds,
                                           disable_auto_x_evaluation=False,
                                           error_on_missing=True)
        return self.cmd(cmd=feature)

    def get_events(self):
        """
        Return a list of the asynchronous events received since the last
        clear_events() call.

        :return: A list of events (the objects returned have an "event" key)
        :raise MonitorLockError: Raised if the lock cannot be acquired
        """
        if not self._acquire_lock():
            raise MonitorLockError("Could not acquire exclusive lock to read "
                                   "QMP events")
        try:
            self._read_objects()
            return self._events[:]
        finally:
            self._lock.release()

    def get_event(self, name):
        """
        Look for an event with the given name in the list of events.

        :param name: The name of the event to look for (e.g. 'RESET')
        :return: An event object or None if none is found
        """
        for e in self.get_events():
            if e.get("event") == name:
                return e

    def human_monitor_cmd(self, cmd="", timeout=CMD_TIMEOUT,
                          debug=True, fd=None):
        """
        Run human monitor command in QMP through human-monitor-command

        :param cmd: human monitor command.
        :param timeout: Time duration to wait for response
        :param debug: Whether to print the commands being sent and responses
        :param fd: file object or file descriptor to pass

        :return: The response to the command
        """
        self._log_command(cmd, debug, extra_str="(via Human Monitor)")

        args = {"command-line": cmd}
        ret = self.cmd("human-monitor-command", args, timeout, False, fd)

        if ret:
            self._log_response(cmd, ret, debug)
        return ret

    def clear_events(self):
        """
        Clear the list of asynchronous events.

        :raise MonitorLockError: Raised if the lock cannot be acquired
        """
        if not self._acquire_lock():
            raise MonitorLockError("Could not acquire exclusive lock to clear "
                                   "QMP event list")
        self._events = []
        self._lock.release()

    def clear_event(self, name):
        """
        Clear a kinds of events in events list only.

        :raise MonitorLockError: Raised if the lock cannot be acquired
        """
        if not self._acquire_lock():
            raise MonitorLockError("Could not acquire exclusive lock to clear "
                                   "QMP event list")
        while True:
            event = self.get_event(name)
            if event:
                self._events.remove(event)
            else:
                break
        self._lock.release()

    def get_greeting(self):
        """
        Return QMP greeting message.
        """
        return self._greeting

    # Command wrappers
    # Note: all of the following functions raise exceptions in a similar manner
    # to cmd().
    def send_args_cmd(self, cmdlines, timeout=CMD_TIMEOUT, convert=True):
        """
        Send a command with/without parameters and return its output.
        Have same effect with cmd function.
        Implemented under the same name for both the human and QMP monitors.
        Command with parameters should in following format e.g.:
        'memsave val=0 size=10240 filename=memsave'
        Command without parameter: 'query-vnc'

        :param cmdlines: Commands send to qemu which is separated by ";". For
                         command with parameters command should send in a string
                         with this format:
                         $command $arg_name=$arg_value $arg_name=$arg_value
        :param timeout: Time duration to wait for (qemu) prompt after command
        :param convert: If command need to convert. For commands not in standard
                        format such as: $command $arg_value
        :return: The response to the command
        :raise MonitorLockError: Raised if the lock cannot be acquired
        :raise MonitorSendError: Raised if the command cannot be sent
        :raise MonitorProtocolError: Raised if no response is received
        """
        cmd_output = []
        for cmdline in cmdlines.split(";"):
            command = cmdline.split()[0]
            if not self._has_command(command):
                if "=" in cmdline:
                    command = cmdline.split()[0]
                    self.verify_supported_hmp_cmd(command)

                    cmdargs = " ".join(cmdline.split()[1:]).split(",")
                    for arg in cmdargs:
                        value = "=".join(arg.split("=")[1:])
                        if arg.split("=")[0] == "cert-subject":
                            value = value.replace('/', ',')

                        command += " " + value
                else:
                    command = cmdline
                cmd_output.append(self.human_monitor_cmd(command))
            else:
                cmdargs = " ".join(cmdline.split()[1:]).split(",")
                args = {}
                for arg in cmdargs:
                    opt = arg.split('=')
                    value = "=".join(opt[1:])
                    try:
                        if re.match("^[0-9]+$", value):
                            # when force convert type to int,exclude 'fd' as bz
                            # 1853538. And the int type convert is not absolute
                            # accurate for other values, if hit problem please
                            # check the expect type of qemu and update.
                            if opt[0] != 'fd':
                                value = int(value)
                        elif re.match("^[0-9]+\.[0-9]*$", value):
                            value = float(value)
                        elif re.findall("true", value, re.I):
                            value = True
                        elif re.findall("false", value, re.I):
                            value = False
                        else:
                            value = value.strip()
                        if opt[0] == "cert-subject":
                            value = value.replace('/', ',')
                        if opt[0]:
                            args[opt[0].strip()] = value
                    except Exception:
                        LOG.debug("Fail to create args, please check cmd")
                cmd_output.append(self.cmd(command, args, timeout=timeout))
        if len(cmd_output) == 1:
            return cmd_output[0]
        return cmd_output

    def quit(self):
        """
        Send "quit" and return the response.
        """
        return self.cmd("quit")

    def info(self, what, debug=True):
        """
        Request info about something and return the response.
        """
        cmd = "query-%s" % what
        if not self._has_command(cmd):
            cmd = "info %s" % what
            return self.human_monitor_cmd(cmd, debug=debug)

        return self.cmd(cmd, debug=debug)

    def query(self, what, debug=True):
        """
        Alias for info.
        """
        return self.info(what, debug)

    def screendump(self, filename, debug=True):
        """
        Request a screendump.

        :param filename: Location for the screendump
        :param debug: Whether to print the commands being sent and responses

        :return: The response to the command
        """
        cmd = "screendump"
        if not self._has_command(cmd):
            self.verify_supported_hmp_cmd(cmd)
            cmdline = "%s %s" % (cmd, filename)
            return self.human_monitor_cmd(cmdline, debug=debug)

        args = {"filename": filename}
        return self.cmd(cmd=cmd, args=args, debug=debug)

    def system_reset(self):
        """ Reset guest system """
        cmd, event = "system_reset", "RESET"
        self.verify_supported_cmd(cmd)
        self.clear_event(event)
        ret = self.cmd(cmd=cmd)
        if not utils_misc.wait_for(lambda: self.get_event(event), timeout=120):
            raise QMPEventError(cmd, event, self.vm.name, self.name)
        return ret

    def sendkey(self, keystr, hold_time=1):
        """
        Send key combination to VM.

        :param keystr: Key combination string
        :param hold_time: Hold time in ms (should normally stay 1 ms)

        :return: The response to the command
        """
        return self.human_monitor_cmd("sendkey %s %s" % (keystr, hold_time))

    def migrate(self, uri, full_copy=False,
                incremental_copy=False, wait=False):
        """
        Migrate.

        :param uri: destination URI
        :param full_copy: If true, migrate with full disk copy
        :param incremental_copy: If true, migrate with incremental disk copy
        :param wait: If true, wait for completion
        :return: The response to the command
        """
        args = {"uri": uri,
                "blk": full_copy,
                "inc": incremental_copy}
        args['uri'] = re.sub('"', "", args['uri'])
        try:
            return self.cmd("migrate", args)
        except QMPCmdError as e:
            if e.data['class'] in ['SockConnectInprogress', 'GenericError']:
                LOG.debug("Migrate socket connection still initializing...")
            else:
                raise e

    def migrate_continue(self, state):
        """
        Continue migration when it's in a paused state.

        :param state: The state the migration is currently expected to be in.
        :return: The response to the command.
        """
        args = {"state": state}
        return self.cmd("migrate-continue", args)

    def migrate_set_speed(self, value):
        """
        Set maximum speed (in bytes/sec) for migrations.

        :param value: Speed in bytes/sec
        :return: The response to the command
        """
        value = cartesian_config.convert_data_size(value, "M")
        args = {"value": value}
        return self.cmd("migrate_set_speed", args)

    def migrate_incoming(self, uri):
        """
        Start an incoming migration, the qemu must have been started
        with -incoming defer.

        :param uri: The Uniform Resource Identifier identifying the
                    source or address to listen on.
        :type uri: str
        """
        return self.cmd("migrate-incoming", {"uri": uri})

    def set_link(self, name, up):
        """
        Set link up/down.

        :param name: Link name
        :param up: Bool value, True=set up this link, False=Set down this link

        :return: The response to the command
        """
        return self.cmd("set_link", {"name": name, "up": up})

    def migrate_set_downtime(self, value):
        """
        Set maximum tolerated downtime (in seconds) for migration.

        :param value: maximum downtime (in seconds)

        :return: The command's output
        """
        args = {"value": value}
        return self.cmd("migrate_set_downtime", args)

    def live_snapshot(self, device, snapshot_file, **kwargs):
        """
        Take a live disk snapshot.

        :param device: the name of the device to generate the snapshot from.
        :param snapshot_file: the target of the new image. A new file will
                              be created if mode is "absolute-paths".
        :param kwargs: optional keyword arguments to pass to func.
        :keyword args (optional):
            format: the format of the snapshot image, default is 'qcow2'.
            mode: whether and how QEMU should create a new image,
            default is 'absolute-paths'.

        :return: The response to the command
        """
        args = {"device": device,
                "snapshot-file": snapshot_file}
        kwargs.update(args)
        if 'format' not in kwargs:
            kwargs.update({"format": "qcow2"})
        if 'mode' not in kwargs:
            kwargs.update({"mode": "absolute-paths"})
        return self.cmd("blockdev-snapshot-sync", kwargs)

    def block_stream(self, device, speed=None, base=None,
                     cmd="block-stream", correct=True, **kwargs):
        """
        Start block-stream job;

        :param device: device ID
        :param speed: int type, limited speed(B/s)
        :param base: base file
        :param correct: auto correct command, correct by default
        :param kwargs: optional keyword arguments
        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        args = {"device": device}
        if speed is not None:
            args["speed"] = speed
        if base:
            args["base"] = base
        kwargs.update(args)
        return self.cmd(cmd, kwargs)

    def block_commit(self, device, speed=None, base=None, top=None,
                     cmd="block-commit", correct=True):
        """
        Start block-commit job

        :param device: device ID
        :param speed: int type, limited speed(B/s)
        :param base: base file
        :param top: top file
        :param cmd: block commit job command
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        args = {"device": device}
        if speed:
            args["speed"] = speed
        if base:
            args["base"] = base
        if top:
            args["top"] = top
        return self.cmd(cmd, args)

    def set_block_job_speed(self, device, speed=0,
                            cmd="block-job-set-speed", correct=True):
        """
        Set limited speed for running job on the device

        :param device: device ID
        :param speed: int type, limited speed(B/s)
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        args = {"device": device,
                "speed": speed}
        return self.cmd(cmd, args)

    def cancel_block_job(self, device, cmd="block-job-cancel", correct=True):
        """
        Cancel running block stream/mirror job on the device

        :param device: device ID
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        args = {"device": device}
        return self.cmd(cmd, args)

    def pause_block_job(self, device, cmd="block-job-pause", correct=True):
        """
        Pause an active block streaming operation.
        :param device: device ID
        :param cmd: pause block job command
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        args = {"device": device}
        return self.cmd(cmd, args)

    def resume_block_job(self, device, cmd="block-job-resume", correct=True):
        """
        Resume a paused block streaming operation.
        :param device: device ID
        :param cmd: resume block job command
        :param correct: auto correct command, correct by default

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        args = {"device": device}
        return self.cmd(cmd, args)

    def query_block_job(self, device):
        """
        Get block job status on the device

        :param device: device ID

        :return: dict about job info, return empty dict if no active job
        """
        output = self.info("block-jobs")
        try:
            job = filter(lambda x: x.get("device") == device, output)
            job = list(job)[0]
        except Exception:
            job = dict()
        return job

    def query_jobs(self):
        """Query block job info """
        return self.query("jobs")

    def query_named_block_nodes(self):
        """Query named block nodes info"""
        cmd = "query-named-block-nodes"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd)

    def get_backingfile(self, device):
        """
        Return "backing_file" path of the device

        :param device: device ID

        :return: string, backing_file path
        """
        backing_file = None
        block_info = self.query("block")
        try:
            image_info = filter(lambda x: x["device"] == device, block_info)
            image_info = list(image_info)[0]
            backing_file = image_info["inserted"].get("backing_file")
        except Exception:
            pass
        return backing_file

    def block_mirror(self, device, target, sync, cmd="drive-mirror",
                     correct=True, **kwargs):
        """
        Start mirror type block device copy job

        :param device: device name to operate on
        :param target: name of new image file
        :param sync: what parts of the disk image should be copied to the
                     destination
        :param cmd: block mirror command
        :param correct: auto correct command, correct by default
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

        :return: The command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        args = {"device": device,
                "target": target}
        if cmd.startswith("__com.redhat"):
            args["full"] = sync
        else:
            args["sync"] = sync
        kwargs.update(args)
        return self.cmd(cmd, kwargs)

    def block_reopen(self, device, new_image_file, image_format,
                     cmd="block-job-complete", correct=True):
        """
        Reopen new target image;

        :param device: device ID
        :param new_image_file: new image file name
        :param image_format: new image file format
        :param cmd: image reopen command
        :param correct: auto correct command, correct by default

        :return: the command's output
        """
        if correct:
            cmd = self.get_workable_cmd(cmd)
        self.verify_supported_cmd(cmd)
        args = {"device": device}
        if cmd.startswith("__"):
            args["new-image-file"] = new_image_file
            args["format"] = image_format
        return self.cmd(cmd, args)

    def getfd(self, fd, name):
        """
        Receives a file descriptor

        :param fd: File descriptor to pass to QEMU
        :param name: File descriptor name (internal to QEMU)

        :return: The response to the command
        """
        args = {"fdname": name}
        return self.cmd("getfd", args, fd=fd)

    def closefd(self, fd, name):
        """
        Close a file descriptor

        :param fd: File descriptor to pass to QEMU
        :param name: File descriptor name (internal to QEMU)

        :return: The response to the command
        """
        args = {"fdname": name}
        return self.cmd("closefd", args, fd=fd)

    def system_wakeup(self):
        """
        Wakeup suspended guest.
        """
        cmd = "system_wakeup"
        qmp_event = "WAKEUP"
        self.verify_supported_cmd(cmd)
        # Clear the event of QMP monitors
        self.clear_event(qmp_event)
        # Send a system_wakeup monitor command
        self.cmd(cmd)
        # Look for WAKEUP QMP event
        if not utils_misc.wait_for(lambda: self.get_event(qmp_event), 120):
            raise QMPEventError(cmd, qmp_event, self.vm.name, self.name)
        LOG.info("%s QMP event received" % qmp_event)

    def nmi(self):
        """
        Inject a NMI on all guest's CPUs.
        """
        return self.cmd("inject-nmi")

    def block_resize(self, device, size, node_name=None):
        """
        Resize the block device size.

        :param device: Block device name.
        :param size: Block device size need to set to. Unit is bytes.
        :param node_name: Graph node name to get the image resized.
        :return: The response to the command.
        """
        cmd = 'block_resize '
        option = ['device', 'node-name', 'size']
        value = [device, node_name, size]
        for opt, val in zip(option, value):
            if val is not None:
                cmd += "{}={},".format(opt, val)
        return self.send_args_cmd(cmd.rstrip(','))

    def eject_cdrom(self, device, force=False):
        """
        Eject media of cdrom and open cdrom door;
        """
        cmd = "eject"
        self.verify_supported_cmd(cmd)
        args = {"device": device, "force": force}
        return self.cmd(cmd, args)

    def change_media(self, device, target):
        """
        Change media of cdrom of drive;
        """
        cmd = "change"
        self.verify_supported_cmd(cmd)
        args = {"device": device, "target": target}
        return self.cmd(cmd, args)

    def blockdev_open_tray(self, dev_id, force=None):
        """
        Opens a block device's tray. If there is a block driver state tree
        inserted as a medium, it will become inaccessible to the guest (but
        it will remain associated to the block device, so closing the tray
        will make it accessible again).

        :param dev_id: The name or QOM path of the guest device.
        :type dev_id: str
        :param force: If false, an eject request will be sent to the guest if
                      it has locked the tray (and the tray will not be opened
                      immediately); if true, the tray will be opened regardless
                      of whether it is locked.
        :type force: bool
        :return: The response of command.
        """
        cmd = "blockdev-open-tray"
        self.verify_supported_cmd(cmd)
        args = {"id": dev_id}
        if force is not None:
            args["force"] = force
        return self.cmd(cmd, args)

    def blockdev_close_tray(self, dev_id):
        """
        Closes a block device's tray. If there is a block driver state tree
        associated with the block device (which is currently ejected), that
        tree will be loaded as the medium.If the tray was already closed
        before, this will be a no-op.

        :param dev_id: The name or QOM path of the guest device.
        :type dev_id: str
        :return: The response of command.
        """
        cmd = "blockdev-close-tray"
        self.verify_supported_cmd(cmd)
        args = {"id": dev_id}
        return self.cmd(cmd, args)

    def blockdev_remove_medium(self, dev_id):
        """
        Removes a medium (a block driver state tree) from a block device. That
        block device's tray must currently be open (unless there is no attached
        guest device).

        :param dev_id: The name or QOM path of the guest device.
        :type dev_id: str
        :return: The response of command.
        """
        cmd = "blockdev-remove-medium"
        self.verify_supported_cmd(cmd)
        args = {"id": dev_id}
        return self.cmd(cmd, args)

    def blockdev_insert_medium(self, dev_id, node_name):
        """
        Inserts a medium (a block driver state tree) into a block device. That
        block device's tray must currently be open (unless there is no attached
        guest device) and there must be no medium inserted already.

        :param dev_id: The name or QOM path of the guest device.
        :type dev_id: str
        :param node_name: The name of a node in the block driver state graph.
        :type node_name: str
        :return: The response of command.
        """
        cmd = "blockdev-insert-medium"
        self.verify_supported_cmd(cmd)
        args = {"id": dev_id, "node-name": node_name}
        return self.cmd(cmd, args)

    def blockdev_change_medium(self, dev_id, filename, fmt=None, mode=None):
        """
        Changes the medium inserted into a block device by ejecting the current
        medium and loading a new image file which is inserted as the new medium
        (this command combines blockdev-open-tray, blockdev-remove-medium,
        blockdev-insert-medium and blockdev-close-tray).

        :param dev_id: The name or QOM path of the guest device.
        :type dev_id: str
        :param filename: The filename of the new image to be loaded.
        :type filename: str
        :param fmt: The format to open the new image.
        :type fmt: str
        :param mode: Change the read-only mode of the device.
        :type mode: str
        :return: The response of command.
        """
        cmd = "blockdev-change-medium"
        self.verify_supported_cmd(cmd)
        args = {"id": dev_id, "filename": filename}
        if fmt is not None:
            args["format"] = fmt
        if mode is not None:
            args["read-only-mode"] = mode
        return self.cmd(cmd, args)

    def blockdev_create(self, job_id, options):
        """
        Create block device image file by qemu

        :param kwargs: dictionary containing required parameters
        :return: block job ID
        :rtype: string
        """
        cmd = "blockdev-create"
        self.verify_supported_cmd(cmd)
        arguments = {"job-id": job_id, "options": options}
        return self.cmd(cmd, arguments)

    def blockdev_add(self, props):
        """
        Creates a new block device.

        :param props: Dictionary with the blockdev-add parameters
                      (property of block device).
        :type props: dict
        :return: The response of command.
        """
        cmd = "blockdev-add"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd, props)

    def blockdev_del(self, node_name):
        """
        Deletes a block device that has been added using blockdev-add.
        The command will fail if the node is attached to a device or is
        otherwise being used.

        :param node_name: Name of the graph node to delete.
        :type node_name: str
        :return: The response of command.
        """
        cmd = "blockdev-del"
        self.verify_supported_cmd(cmd)
        args = {"node-name": node_name}
        return self.cmd(cmd, args)

    def blockdev_backup(self, options):
        """
        Backup block device via QMP command blockdev-backup

        :param kwargs: dictionary containing required parameters
        :return: block job ID
        :rtype: string
        """
        cmd = "blockdev-backup"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd, options)

    def job_dismiss(self, identifier):
        """Dismiss a block job"""
        cmd = "job-dismiss"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd, {"id": identifier})

    def qom_set(self, path, qproperty, qvalue):
        """
        Set the property to value for the device.

        :param path: device path.
        :param qproperty: property which needs set.
        :param qvalue: value of the property.
        """
        cmd = "qom-set"
        self.verify_supported_cmd(cmd)
        args = {"path": path, "property": qproperty, "value": qvalue}
        return self.cmd(cmd, args)

    def qom_get(self, path, qproperty):
        """
        Get output of cmd "qom-get".

        :param path: device path.
        :param qproperty: property which needs set.

        :return: the output of cmd "qom-get".
        """
        cmd = "qom-get"
        self.verify_supported_cmd(cmd)
        args = {"path": path, "property": qproperty}
        return self.cmd(cmd, args)

    def balloon(self, size):
        """
        Balloon VM memory to size bytes;

        :param size: int type values.
        """
        cmd = "balloon"
        qmp_event = "BALLOON_CHANGE"
        self.verify_supported_cmd(cmd)
        # Clear the event list of QMP monitors
        self.clear_event(qmp_event)
        # Send a balloon monitor command
        self.send_args_cmd("%s value=%s" % (cmd, size))
        # Look for BALLOON QMP events
        if not utils_misc.wait_for(lambda: self.get_event(qmp_event), 120):
            raise QMPEventError(cmd, qmp_event, self.vm.name, self.name)
        LOG.info("%s QMP event received" % qmp_event)

    def _get_migrate_capability(self, capability,
                                disable_auto_x_evaluation=True):
        if self._supported_migrate_capabilities is None:
            ret = self.query("migrate-capabilities")
            self._supported_migrate_capabilities = set(_["capability"]
                                                       for _ in ret)
        return super(QMPMonitor, self)._get_migrate_capability(capability,
                                                               disable_auto_x_evaluation)

    def set_migrate_capability(self, state, capability,
                               disable_auto_x_evaluation=True):
        """
        Set the capability of migrate to state.

        :param state: Bool value of capability.
        :param capability: capability which need to set.
        :param disable_auto_x_evaluation: Whether to automatically choose
                                          feature with/without "x-" prefix
        :raise MonitorNotSupportedMigCapError: if the capability is unsettable
        """
        capability = self._get_migrate_capability(capability,
                                                  disable_auto_x_evaluation)
        cmd = "migrate-set-capabilities"
        self.verify_supported_cmd(cmd)
        args = {"capabilities": [{"state": state, "capability": capability}]}
        # If the capability doesn't exist or can't be used in this situation
        # we'll get a GenericError with text explaining, but it's not always
        # clear if it's another reason for the error
        try:
            return self.cmd(cmd, args)
        except QMPCmdError as exc:
            if disable_auto_x_evaluation:
                raise
            # Try it again with/without "x-" prefix
            capability2 = x_non_x_feature(capability)
            args = {"capabilities": [{"state": state,
                                      "capability": capability2}]}
            try:
                return self.cmd(cmd, args)
            except QMPCmdError as exc2:
                LOG.debug("Error in set_migrate_capability for %s: %s",
                          capability, exc)
                LOG.debug("Error in set_migrate_capability for %s: "
                          "%s", capability2, exc2)
                if exc.data['class'] == exc2.data['class'] == 'GenericError':
                    msg = ("set capability failed for %s (%s) as well as %s "
                           "(%s)" % (capability, exc, capability2, exc2))
                    raise MonitorNotSupportedMigCapError(msg)
                else:   # raise the non-generic-error exception
                    if exc.data['class'] == 'GenericError':
                        raise exc2
                    else:
                        raise exc

    def get_migrate_capability(self, capability,
                               disable_auto_x_evaluation=True):
        """
        Get the state of migrate-capability.

        :param capability: capability which need to get.
        :return: the state of migrate-capability.
        :note: automatically checks for "x-"/non-"x-" variant of the cap.
        :raise MonitorNotSupportedMigCapError: if the capability is unknown
        """
        capability = self._get_migrate_capability(capability,
                                                  disable_auto_x_evaluation)
        capability_infos = self.query("migrate-capabilities")
        for item in capability_infos:
            if item["capability"] == capability:
                return item["state"]
        raise MonitorNotSupportedMigCapError("Unknown capability %s" %
                                             capability)

    def set_migrate_cache_size(self, value):
        """
        Set the cache size of migrate to value.

        :param value: the cache size to set.
        """
        cmd = "migrate-set-cache-size"
        self.verify_supported_cmd(cmd)
        args = {"value": value}
        return self.cmd(cmd, args)

    def get_migrate_cache_size(self):
        """
        Get the xbzrel cache size.
        """
        return self.query("migrate-cache-size")

    def _get_migrate_parameter(self, parameter, error_on_missing=False,
                               disable_auto_x_evaluation=True):
        if self._supported_migrate_parameters is None:
            ret = self.query("migrate-parameters")
            self._supported_migrate_parameters = ret.keys()
        return super(QMPMonitor, self)._get_migrate_parameter(parameter,
                                                              error_on_missing,
                                                              disable_auto_x_evaluation)

    def set_migrate_parameter(self, parameter, value, error_on_missing=False,
                              disable_auto_x_evaluation=True):
        """
        Set the parameters of migrate.

        :param parameter: the parameter which need to set.
        :param value: the value of parameter
        :param disable_auto_x_evaluation: Whether to automatically choose
                                          param with/without "x-" prefix
        """
        cmd = "migrate-set-parameters"
        self.verify_supported_cmd(cmd)
        parameter = self._get_migrate_parameter(parameter, error_on_missing,
                                                disable_auto_x_evaluation)
        args = {parameter: value}
        return self.cmd(cmd, args)

    def get_migrate_parameter(self, parameter, disable_auto_x_evaluation=True):
        """
        Get the value of parameter.

        :param parameter: parameter which need to get.
        :param disable_auto_x_evaluation: Whether to automatically choose
                                          param with/without "x-" prefix
        """
        parameter_info = self.query("migrate-parameters")
        parameter = self._get_migrate_parameter(parameter,
                                                disable_auto_x_evaluation=disable_auto_x_evaluation)
        if parameter in parameter_info:
            return parameter_info[parameter]
        return False

    def get_migrate_progress(self):
        """
        Return the transfered / remaining ram ratio

        :return: percentage remaining for RAM transfer
        """
        migration_info = self.query("migrate")
        status = migration_info["status"]
        if "ram" in migration_info:
            ram_stats = migration_info["ram"]
            rem = ram_stats["remaining"]
            total = ram_stats["total"]
            ret = 100.0 - 100.0 * rem / total
            LOG.debug("Migration progress: %s%%", ret)
            return ret
        else:
            if status == "completed":
                LOG.debug("Migration progress: 100%")
                return 100
            elif status == "setup":
                LOG.debug("Migration progress: 0%")
                return 0
            else:
                raise MonitorError(
                    "Unable to parse migration progress:\n%s" % status)

    def migrate_start_postcopy(self):
        """
        Switch into postcopy migrate mode
        """
        return self.cmd("migrate-start-postcopy")

    def system_powerdown(self):
        """
        Requests that a guest perform a powerdown operation.
        """
        cmd = "system_powerdown"
        qmp_event = "POWERDOWN"
        self.verify_supported_cmd(cmd)
        # Clear the event list of QMP monitors
        self.clear_event(qmp_event)
        # Send a powerdown monitor command
        self.cmd(cmd)
        # Look for POWERDOWN QMP events
        if not utils_misc.wait_for(lambda: self.get_event(qmp_event), 120):
            raise QMPEventError(cmd, qmp_event, self.vm.name, self.name)
        LOG.info("%s QMP event received" % qmp_event)

    def transaction(self, job_list):
        """
        Atomically operate on a group of one or more block devices.

        :param job_list: List of block jobs information.

        :return: nothing on success
                 If @device is not a valid block device, DeviceNotFound
        """
        transaction_args = {"actions": job_list}
        return self.cmd("transaction", transaction_args)

    def operate_dirty_bitmap(self, operation, node, name, granularity=65536):
        """
        Add, remove or clear a dirty bitmap.

        NOTE: this method is deprecated, please use corresponding dedicated
              methods:
              block_dirty_bitmap_add
              block_dirty_bitmap_remove
              block_dirty_bitmap_clear
              block_dirty_bitmap_enable
              block_dirty_bitmap_disable

        :param operation: operations to bitmap, can be 'add', 'remove', and 'clear'
        :param node: device/node on which to operate dirty bitmap
        :param name: name of the dirty bitmap to operate
        :param granularity: granularity to track writes with
        """
        cmd = "block-dirty-bitmap-%s" % operation
        if not self._has_command(cmd):
            cmd += "x-"
        return self._operate_dirty_bitmap(cmd, node, name,
                                          granularity=granularity)

    def _operate_dirty_bitmap(self, cmd, node, name, **kargs):
        """
        Operate dirty bitmap.

        :param cmd: command to operate bitmap
        :param node: device node
        :param name: name of the dirty bitmap to operate
        """
        self.verify_supported_cmd(cmd)
        args = {"node": node, "name": name}
        args.update(self._build_args(**kargs))
        return self.cmd(cmd, args)

    def block_dirty_bitmap_add(self, node, name, disabled=None,
                               granularity=None, persistent=None):
        """
        Add a dirty bitmap.

        :param node: device node
        :param name: bitmap name
        :param disabled: bitmap created in disabled state
        :param granularity: segment size
        :param persistent: persistent through QEMU shutdown
        """
        kwargs = {"granularity": granularity,
                  "disabled": disabled,
                  "persistent": persistent}
        cmd = "block-dirty-bitmap-add"
        try:
            return self._operate_dirty_bitmap(cmd, node, name, **kwargs)
        except QMPCmdError as e:
            if "'disabled' is unexpected" in str(e):
                kwargs["x-disabled"] = kwargs.pop("disabled")
            else:
                raise e
        return self._operate_dirty_bitmap(cmd, node, name, **kwargs)

    def block_dirty_bitmap_remove(self, node, name):
        """
        Remove a dirty bitmap.
        """
        cmd = "block-dirty-bitmap-remove"
        return self._operate_dirty_bitmap(cmd, node, name)

    def block_dirty_bitmap_clear(self, node, name):
        """
        Reset a dirty bitmap.
        """
        cmd = "block-dirty-bitmap-clear"
        return self._operate_dirty_bitmap(cmd, node, name)

    def block_dirty_bitmap_merge(self, node, src_bitmaps, dst_bitmap):
        """
        Merge source bitmaps into target bitmap in node

        :param node: device ID or node-name
        :param src_bitmaps: source bitmap list
        :param dst_bitmap: target bitmap name
        """
        cmd = "block-dirty-bitmap-merge"
        self.verify_supported_cmd(cmd)
        args = {"node": node, "bitmaps": src_bitmaps, "target": dst_bitmap}
        return self.cmd(cmd, args)

    def x_block_dirty_bitmap_merge(self, node, src_bitmap, dst_bitmap):
        """
        Merge source bitmaps to target bitmap for given node

        :param string node: block device node name
        :parma list src_bitmaps: list of source bitmaps
        :param string dst_bitmap: target bitmap name
        :raise: MonitorNotSupportedCmdError if 'block-dirty-bitmap-mege' and
                'x-block-dirty-bitmap-mege' commands not supported by QMP
                monitor.
        """
        cmd = "x-block-dirty-bitmap-merge"
        self.verify_supported_cmd(cmd)
        args = {"node": node, "src_name": src_bitmap, "dst_name": dst_bitmap}
        return self.cmd(cmd, args)

    def block_dirty_bitmap_enable(self, node, name):
        """
        Enable a dirty bitmap.
        """
        cmd = "block-dirty-bitmap-enable"
        return self._operate_dirty_bitmap(cmd, node, name)

    def x_block_dirty_bitmap_enable(self, node, name):
        """
        Enable a dirty bitmap.
        """
        cmd = "x-block-dirty-bitmap-enable"
        return self._operate_dirty_bitmap(cmd, node, name)

    def block_dirty_bitmap_disable(self, node, name):
        """
        Disable a dirty bitmap.
        """
        cmd = "block-dirty-bitmap-disable"
        return self._operate_dirty_bitmap(cmd, node, name)

    def x_block_dirty_bitmap_disable(self, node, name):
        """
        Disable a dirty bitmap.
        """
        cmd = "x-block-dirty-bitmap-disable"
        return self._operate_dirty_bitmap(cmd, node, name)

    def debug_block_dirty_bitmap_sha256(self, node, bitmap):
        """
        get sha256 of bitmap

        :param string node: node name
        :param string bitmap: bitmap name
        """
        cmd = "debug-block-dirty-bitmap-sha256"
        self.verify_supported_cmd(cmd)
        args = {"node": node, "name": bitmap}
        return self.cmd(cmd, args)

    def x_debug_block_dirty_bitmap_sha256(self, node, bitmap):
        """
        get sha256 of bitmap

        :param string node: node name
        :param string bitmap: bitmap name
        """
        cmd = "x-debug-block-dirty-bitmap-sha256"
        self.verify_supported_cmd(cmd)
        args = {"node": node, "name": bitmap}
        return self.cmd(cmd, args)

    def drive_backup(self, device, target, format, sync, speed=0,
                     mode='absolute-paths', bitmap=''):
        """
        Start a point-in-time copy of a block device to a new destination.

        :param device: the device name or node-name of a root node which should be copied
        :param target: the target of the new image
        :param format: the format of the new destination, default is to probe if 'mode' is
            'existing', else the format of the source
        :param sync:  what parts of the disk image should be copied to the destination;
            possibilities include "full" for all the disk, "top" for only the sectors
            allocated in the topmost image, "incremental" for only the dirty sectors in
            the bitmap, or "none" to only replicate new I/O
        :param speed: the maximum speed, in bytes per second
        :param mode: whether and how QEMU should create a new image
            (NewImageMode, optional, default 'absolute-paths')
        :param bitmap: dirty bitmap name for sync==incremental. Must be present if sync
            is "incremental", must NOT be present otherwise
        """
        cmd = "drive-backup"
        self.verify_supported_cmd(cmd)
        args = {"device": device,
                "target": target,
                "format": format,
                "sync": sync,
                "mode": mode}
        if sync.lower() == "incremental":
            args["bitmap"] = bitmap
        if speed:
            args["speed"] = speed
        return self.cmd(cmd, args)

    def press_release_key(self, key, down=True):
        """
        Press & hold or release a certain key for the VM via QMP monitor.

        :param key: a single key string
        :param down: a boolean value indicated whether the key should be
            pressed down or released. If down is True, the key will be kept
            pressing down until an call to this function with down=False
            is made, or when the VM is rebooted or destroyed.
        :return: the result of the command 'input-send-event'
        """
        cmd = "input-send-event"
        self.verify_supported_cmd(cmd)
        args = {"events": [{
            "type": "key",
            "data": {
                "down": down,
                "key": {
                    "type": "qcode",
                    "data": key
                }}}]}
        return self.cmd(cmd, args)

    def query_mice(self):
        """
        Query active mouse device information.
        """
        return self.cmd("query-mice")

    def input_send_event(self, events, device=None, head=None):
        """
        Send input event(s) to guest.

        :param device: display device to send event(s) to.
        :param head: head to send event(s) to, in case the
                     display device supports multiple scanouts.
        :param events: List of InputEvent union.
        """
        cmd = "input-send-event"
        self.verify_supported_cmd(cmd)
        arguments = dict()
        if device:
            arguments["device"] = device
        if head:
            arguments["head"] = int(head)
        arguments["events"] = events
        return self.cmd(cmd, arguments)

    def nbd_server_start(self, server, tls_creds=None, tls_authz=None):
        """
        Start an NBD server listening on the given host and port.
        :param server: {'host': xx, 'port': 'type': 'inet'} or
                       {'path': xx, 'type': 'unix'}
        :param tls_creds: ID of the TLS credentials object (since 2.6).
        :param tls_authz: ID of the QAuthZ authorization object used to
                          validate the client's x509 distinguished name.
                          (since 4.0)
        """
        cmd = "nbd-server-start"
        self.verify_supported_cmd(cmd)
        arguments = {
            "addr": {
                "type": server.pop("type"),
                "data": server
            }
        }
        if tls_creds:
            arguments["tls-creds"] = tls_creds
        if tls_authz:
            arguments["tls-authz"] = tls_authz
        return self.cmd(cmd, arguments)

    def nbd_server_add(self, device, export_name=None,
                       writable=None, bitmap=None):
        """
        Export a block node to QEMU's embedded NBD server.
        :param device: The device name or node name to be exported
        :param export_name: Export name. If unspecified, the device name
                            is used as the export name.
        :param writable: Whether clients should be able to write to the
                         device via the NBD connection, 'yes' or 'no'
        :param bitmap: Also export the dirty bitmap reachable from device,
                       so the NBD client can use NBD_OPT_SET_META_CONTEXT
                       with 'qemu:dirty-bitmap:NAME' to inspect the bitmap.
                       (since 4.0)
        """
        cmd = "nbd-server-add"
        self.verify_supported_cmd(cmd)
        arguments = dict()
        arguments["device"] = device
        if export_name:
            arguments["name"] = export_name
        if writable:
            arguments["writable"] = writable == "yes"
        if bitmap:
            arguments["bitmap"] = bitmap
        return self.cmd(cmd, arguments)

    def nbd_server_remove(self, export_name, remove_mode=None):
        """
        Remove NBD export by name.
        :param export_name: Export name.
        :param remove_mode: 'safe': Remove export if there are no existing
                                    connections, fail otherwise.(default)
                            'hard': Drop all connections immediately and
                                    remove export.
        """
        cmd = "nbd-server-remove"
        self.verify_supported_cmd(cmd)
        arguments = dict()
        arguments["name"] = export_name
        if remove_mode:
            arguments["mode"] = remove_mode
        return self.cmd(cmd, arguments)

    def nbd_server_stop(self):
        """
        Stop QEMU's embedded NBD server, and unregister all devices
        previously added via nbd-server-add
        """
        cmd = "nbd-server-stop"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd)

    def set_numa_node(self, option_type, **kwargs):
        """
        Run "set-numa-node" command and return the response

        :params option_type: the type to be set, such as 'dist', 'node', 'cpu',
                             'hmat-lb' and 'hmat-cache'
        :params kwargs: keyword arguments for the specified type
        """
        cmd = "set-numa-node"
        self.verify_supported_cmd(cmd)
        args = {'type': option_type}
        args.update(self._build_args(**kwargs))
        return self.cmd(cmd, args)

    def netdev_add(self, backend, name, **kwargs):
        """
        Add a network backend.

        :param backend: Type of network backend.
        :param name: Netdev ID.
        """
        args = {"type": backend, "id": name}
        args.update(self._build_args(**kwargs))
        return self.cmd("netdev_add", args)

    def netdev_del(self, name):
        """
        Remove a network backend.

        :param name: Netdev ID.
        """
        return self.cmd("netdev_del", {"id": name})

    def blockdev_reopen(self, props):
        """
        Reopens a block device using the given set of options.

        :param props: Dictionary of command options
        """
        cmd = "blockdev-reopen"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd, props)

    def x_blockdev_reopen(self, props):
        """
        Reopens a block device using the given set of options.

        :param props: Dictionary of command options
        """
        cmd = "x-blockdev-reopen"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd, props)

    def block_export_add(self, uid, export_type, node_name,
                         iothread=None, fixed_iothread=None,
                         writable=None, writethrough=None, **kwargs):
        """
        Create a new block export. (since 5.2)

        :param uid: A unique identifier for the block export
                    (across all export types)
        :param export_type: Name of block export types, such as 'nbd',
                            'vhost-user-blk' (since 5.2), 'fuse' (since 6.0)
                            (please refer to BlockExportType)
        :param node_name: The node name of the block node to be exported
        :param iothread: The name of the iothread object where the export
                         runs. The default is to use the thread currently
                         associated with the block node.
        :param fixed_iothread: True prevents the block node from being moved
                               to another thread while the export is active.
                               If true and iothread is given, export creation
                               fails if the block node cannot be moved to the
                               iothread. (default false)
        :param writable: True if clients should be able to write to the export
                         (default false)
        :param writethrough: True makes caches flushed after every write to the
                             export before completion is signalled.
                             (default: false)
        :params kwargs: keyword arguments for the specified export_type
                        (please refer to BlockExportOptions)
        """
        cmd = "block-export-add"
        self.verify_supported_cmd(cmd)
        arguments = {'type': export_type, 'id': uid, 'node-name': node_name}
        if writable is not None:
            arguments["writable"] = writable
        if writethrough is not None:
            arguments["writethrough"] = writethrough
        if iothread is not None:
            arguments["iothread"] = iothread
        if fixed_iothread is not None:
            arguments["fixed-iothread"] = fixed_iothread
        arguments.update(self._build_args(**kwargs))
        return self.cmd(cmd, arguments)

    def block_export_del(self, uid, mode=None):
        """
        Request to remove a block export. (Since 5.2)

        This drops the user's reference to the export, but the export may
        still stay around after this command returns until the shutdown of
        the export has completed.
        Note that BLOCK_EXPORT_DELETED will be emitted when a block export
        is removed and its id can be reused.
        :param uid: Block export id
        :param mode: Mode for removing a block export,
                     'safe': Remove export if there are no existing
                             connections, fail otherwise (default)
                     'hard': Drop all connections immediately and remove export
                     (please refer to BlockExportRemoveMode)
        """
        cmd = "block-export-del"
        self.verify_supported_cmd(cmd)
        arguments = {'id': uid}
        if mode:
            arguments['mode'] = mode
        return self.cmd(cmd, arguments)

    def query_block_exports(self):
        """
        Query all block exports. (Since 5.2)

        :return: A list of BlockExportInfo describing all block exports
        """
        cmd = "query-block-exports"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd)

    def query_cpu_model_expansion(self, cpu_model):
        """
        Query all properties with the provided CPU model.

        :param cpu_model: CPU model supported by qemu
        :return: A list of all properties
        """
        cmd = "query-cpu-model-expansion"
        self.verify_supported_cmd(cmd)
        return self.cmd(cmd, {"type": "full",
                              "model": {"name": cpu_model}})["model"]["props"]
