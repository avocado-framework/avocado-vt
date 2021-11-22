"""
Interfaces to the virt agent.

:copyright: 2008-2012 Red Hat Inc.
"""

import socket
import time
import logging
import random
import base64
try:
    import json
except ImportError:
    logging.getLogger('avocado.app').warning(
        "Could not import json module. virt agent functionality disabled.")

from avocado.utils import process

from virttest import error_context
from virttest.qemu_monitor import Monitor, MonitorError


import six

LOG = logging.getLogger('avocado.' + __name__)


class VAgentError(MonitorError):
    pass


class VAgentConnectError(VAgentError):
    pass


class VAgentSocketError(VAgentError):

    def __init__(self, msg, e):
        VAgentError.__init__(self)
        self.msg = msg
        self.e = e

    def __str__(self):
        return "%s    (%s)" % (self.msg, self.e)


class VAgentLockError(VAgentError):
    pass


class VAgentProtocolError(VAgentError):
    pass


class VAgentNotSupportedError(VAgentError):
    pass


class VAgentCmdError(VAgentError):

    def __init__(self, cmd, args, data):
        VAgentError.__init__(self)
        self.ecmd = cmd
        self.eargs = args
        self.edata = data

    def __str__(self):
        return ("Virt Agent command %r failed    (arguments: %r,    "
                "error message: %r)" % (self.ecmd, self.eargs, self.edata))


class VAgentCmdNotSupportedError(VAgentError):

    def __init__(self, cmd):
        VAgentError.__init__(self)
        self.ecmd = cmd

    def __str__(self):
        return("The command %s is not supported by the current version qga"
               % self.ecmd)


class VAgentSyncError(VAgentError):

    def __init__(self, vm_name):
        VAgentError.__init__(self)
        self.vm_name = vm_name

    def __str__(self):
        return "Could not sync with guest agent in vm '%s'" % self.vm_name


class VAgentSuspendError(VAgentError):
    pass


class VAgentSuspendUnknownModeError(VAgentSuspendError):

    def __init__(self, mode):
        VAgentSuspendError.__init__(self)
        self.mode = mode

    def __str__(self):
        return "Not supported suspend mode '%s'" % self.mode


class VAgentFreezeStatusError(VAgentError):

    def __init__(self, vm_name, status, expected):
        VAgentError.__init__(self)
        self.vm_name = vm_name
        self.status = status
        self.expected = expected

    def __str__(self):
        return ("Unexpected guest FS status '%s' (expected '%s') in vm "
                "'%s'" % (self.status, self.expected, self.vm_name))


class QemuAgent(Monitor):

    """
    Wraps qemu guest agent commands.
    """

    READ_OBJECTS_TIMEOUT = 5
    CMD_TIMEOUT = 20
    RESPONSE_TIMEOUT = 20
    PROMPT_TIMEOUT = 20
    FSFREEZE_TIMEOUT = 90

    SERIAL_TYPE_VIRTIO = "virtio"
    SERIAL_TYPE_ISA = "isa"
    SUPPORTED_SERIAL_TYPE = [SERIAL_TYPE_VIRTIO, SERIAL_TYPE_ISA]

    SHUTDOWN_MODE_POWERDOWN = "powerdown"
    SHUTDOWN_MODE_REBOOT = "reboot"
    SHUTDOWN_MODE_HALT = "halt"

    SUSPEND_MODE_DISK = "disk"
    SUSPEND_MODE_RAM = "ram"
    SUSPEND_MODE_HYBRID = "hybrid"

    FSFREEZE_STATUS_FROZEN = "frozen"
    FSFREEZE_STATUS_THAWED = "thawed"

    def __init__(self, vm, name, serial_type, gagent_params,
                 get_supported_cmds=False, suppress_exceptions=False):
        """
        Connect to the guest agent socket, Also make sure the json
        module is available.

        :param vm: The VM object who has this GuestAgent.
        :param name: Guest agent identifier.
        :param serial_type: Specific which serial type (firtio or isa) guest
                agent will use.
        :param gagent_params: Dictionary with guest agent test params, content
               like {'monitor_filename': filename}
        :param get_supported_cmds: Try to get supported cmd list when initiation.
        :param suppress_exceptions: If True, ignore VAgentError exception.

        :raise VAgentConnectError: Raised if the connection fails and
                suppress_exceptions is False
        :raise VAgentNotSupportedError: Raised if the serial type is
                neither 'virtio' nor 'isa' and suppress_exceptions is False
        :raise VAgentNotSupportedError: Raised if json isn't available and
                suppress_exceptions is False
        """
        try:
            if serial_type not in self.SUPPORTED_SERIAL_TYPE:
                raise VAgentNotSupportedError("Not supported serial type: "
                                              "'%s'" % serial_type)

            Monitor.__init__(self, vm, name, gagent_params)
            # Make sure json is available
            try:
                json
            except NameError:
                raise VAgentNotSupportedError("guest agent requires the json"
                                              " module (Python 2.6 and up)")

            # Set a reference to the VM object that has this GuestAgent.
            self.vm = vm

            if get_supported_cmds:
                self._get_supported_cmds()

        # pylint: disable=E0712
        except VAgentError as e:
            self._close_sock()
            if suppress_exceptions:
                LOG.warn(e)
            else:
                raise

    # Methods only used inside this class
    def _build_cmd(self, cmd, args=None):
        obj = {"execute": cmd}
        if args is not None:
            obj["arguments"] = args
        return obj

    def _read_objects(self, timeout=READ_OBJECTS_TIMEOUT):
        """
        Read lines from the guest agent socket and try to decode them.
        Stop when all available lines have been successfully decoded, or when
        timeout expires. Return all decoded objects.

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
                if line[0:1] == b'\xff':
                    line = line[1:]
                objs += [json.loads(line)]
                self._log_lines(line.decode(errors="replace"))
            except Exception:
                pass
        return objs

    def _send(self, data):
        """
        Send raw data without waiting for response.

        :param data: Data to send
        :raise VAgentSocketError: Raised if a socket error occurs
        """
        try:
            self._socket.sendall(data)
            self._log_lines(data.decode(errors="replace"))
        except socket.error as e:
            raise VAgentSocketError("Could not send data: %r" % data, e)

    def _get_response(self, timeout=RESPONSE_TIMEOUT):
        """
        Read a response from the guest agent socket.

        :param id: If not None, look for a response with this id
        :param timeout: Time duration to wait for response
        :return: The response dict
        """
        end_time = time.time() + timeout
        while self._data_available(end_time - time.time()):
            for obj in self._read_objects():
                if isinstance(obj, dict):
                    if "return" in obj or "error" in obj:
                        return obj
        # Return empty dict when timeout.
        return {}

    def _sync(self, sync_mode="guest-sync", timeout=RESPONSE_TIMEOUT * 3):
        """
        Helper for guest agent socket sync.

        The guest agent doesn't provide a command id in its response,
        so we have to send 'guest-sync' cmd by ourselves to keep the
        socket synced.

        :param timeout: Time duration to wait for response
        :param sync_mode: sync or sync-delimited
        :return: True if socket is synced.
        """
        def check_result(response):
            if response:
                self._log_response(cmd, r)
            if "return" in response:
                return response["return"]
            if "error" in response:
                raise VAgentError("Get an error message when waiting for sync"
                                  " with qemu guest agent, check the debug log"
                                  " for the future message,"
                                  " detail: '%s'" % r["error"])

        cmd = sync_mode
        rnd_num = random.randint(1000, 9999)
        args = {"id": rnd_num}
        self._log_command(cmd)
        cmdobj = self._build_cmd(cmd, args)
        data = json.dumps(cmdobj) + "\n"
        # Send command
        r = self.cmd_raw(data)
        if check_result(r) == rnd_num:
            return True

        # We don't get the correct response of 'guest-sync' cmd,
        # thus wait for the response until timeout.
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            r = self._get_response()
            if check_result(r) == rnd_num:
                return True
        return False

    def _get_supported_cmds(self):
        """
        Get supported qmp cmds list.
        """
        synced = self._sync()
        if not synced:
            raise VAgentSyncError(self.vm.name)
        cmds = self.guest_info()
        if cmds and "supported_commands" in cmds:
            cmd_list = cmds["supported_commands"]
            self._supported_cmds = [n["name"] for n in cmd_list if
                                    isinstance(n, dict) and "name" in n]

        if not self._supported_cmds:
            # If initiation fails, set supported list to a None-only list.
            self._supported_cmds = [None]
            LOG.warn("Could not get supported guest agent cmds list")

    def check_has_command(self, cmd):
        """
        Check whether guest agent support 'cmd'.

        :param cmd: command string which will be checked.

        :return: True if cmd is supported, False if not supported.
        """
        # Initiate supported cmds list if it's empty.
        if not self._supported_cmds:
            self._get_supported_cmds()

        # If the first element in supported cmd list is 'None', it means
        # autotest fails to get the cmd list, so bypass cmd checking.
        if self._supported_cmds[0] is None:
            return True

        if cmd and cmd in self._supported_cmds:
            return True
        raise VAgentCmdNotSupportedError(cmd)

    def _log_command(self, cmd, debug=True, extra_str=""):
        """
        Print log message being sent.

        :param cmd: Command string.
        :param debug: Whether to print the commands.
        :param extra_str: Extra string would be printed in log.
        """
        if self.debug_log or debug:
            LOG.debug("(vagent %s) Sending command '%s' %s",
                      self.name, cmd, extra_str)

    def _log_response(self, cmd, resp, debug=True):
        """
        Print log message for guest agent cmd's response.

        :param cmd: Command string.
        :param resp: Response from guest agent command.
        :param debug: Whether to print the commands.
        """
        def _log_output(o, indent=0):
            LOG.debug("(vagent %s)    %s%s", self.name, " " * indent, o)

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
            LOG.debug("(vagent %s) Response to '%s' "
                      "(re-formatted)", self.name, cmd)
            if isinstance(resp, dict):
                _dump_dict(resp)
            elif isinstance(resp, list):
                _dump_list(resp)
            else:
                for l in str(resp).splitlines():
                    _log_output(l)

    # Public methods
    def cmd(self, cmd, args=None, timeout=CMD_TIMEOUT, debug=True,
            success_resp=True):
        """
        Send a guest agent command and return the response if success_resp.

        :param cmd: Command to send
        :param args: A dict containing command arguments, or None
        :param timeout: Time duration to wait for response
        :param debug: Whether to print the commands being sent and responses
        :param fd: file object or file descriptor to pass

        :return: The response received

        :raise VAgentLockError: Raised if the lock cannot be acquired
        :raise VAgentSocketError: Raised if a socket error occurs
        :raise VAgentProtocolError: Raised if no response is received
        :raise VAgentCmdError: Raised if the response is an error message
        """
        self._log_command(cmd, debug)
        # Send command
        cmdobj = self._build_cmd(cmd, args)
        data = json.dumps(cmdobj) + "\n"
        r = self.cmd_raw(data, timeout, success_resp)

        if not success_resp:
            return ""

        if "return" in r:
            ret = r["return"]
            if ret:
                self._log_response(cmd, ret, debug)
            return ret
        if "error" in r:
            raise VAgentCmdError(cmd, args, r["error"])

    def cmd_raw(self, data, timeout=CMD_TIMEOUT, success_resp=True):
        """
        Send a raw bytes to the guest agent and return the response.
        Unlike cmd(), return the raw response dict without performing
        any checks on it.

        :param data: The data to send
        :param timeout: Time duration to wait for response
        :return: The response received
        :raise VAgentLockError: Raised if the lock cannot be acquired
        :raise VAgentSocketError: Raised if a socket error occurs
        :raise VAgentProtocolError: Raised if no response is received
        """
        if not self._acquire_lock():
            raise VAgentLockError("Could not acquire exclusive lock to send "
                                  "data: %r" % data)

        try:
            self._read_objects()
            self._send(data.encode())
            # Return directly for some cmd without any response.
            if not success_resp:
                return {}

            # Read response
            r = self._get_response(timeout)

        finally:
            self._lock.release()

        if r is None:
            raise VAgentProtocolError(
                "Received no response to data: %r" % data)
        return r

    def cmd_obj(self, obj, timeout=CMD_TIMEOUT):
        """
        Transform a Python object to JSON, send the resulting string to
        the guest agent, and return the response.
        Unlike cmd(), return the raw response dict without performing any
        checks on it.

        :param obj: The object to send
        :param timeout: Time duration to wait for response
        :return: The response received
        :raise VAgentLockError: Raised if the lock cannot be acquired
        :raise VAgentSocketError: Raised if a socket error occurs
        :raise VAgentProtocolError: Raised if no response is received
        """
        return self.cmd_raw(json.dumps(obj) + "\n", timeout)

    def verify_responsive(self):
        """
        Make sure the guest agent is responsive by sending a command.
        """
        cmd = "guest-ping"
        if self.check_has_command(cmd):
            self.cmd(cmd=cmd, debug=False)

    @error_context.context_aware
    def shutdown(self, mode=SHUTDOWN_MODE_POWERDOWN):
        """
        Send "guest-shutdown", this cmd would not return any response.

        :param mode: Specify shutdown mode, now qemu guest agent supports
                     'powerdown', 'reboot', 'halt' 3 modes.
        :return: True if shutdown cmd is sent successfully, False if
                 'shutdown' is unsupported.
        """
        cmd = "guest-shutdown"
        self.check_has_command(cmd)
        args = None
        if mode in [self.SHUTDOWN_MODE_POWERDOWN, self.SHUTDOWN_MODE_REBOOT,
                    self.SHUTDOWN_MODE_HALT]:
            args = {"mode": mode}
        try:
            self.cmd(cmd=cmd, args=args)
        except VAgentProtocolError:
            pass

    @error_context.context_aware
    def sync(self, sync_mode="guest-sync"):
        """
        Sync guest agent with cmd 'guest-sync' or 'guest-sync-delimited'.
        """
        cmd = sync_mode
        self.check_has_command(cmd)

        synced = self._sync(sync_mode)
        if not synced:
            raise VAgentSyncError(self.vm.name)

    @error_context.context_aware
    def set_user_password(self, password, crypted=False, username="root"):
        """
        Set the new password for the user
        """
        cmd = "guest-set-user-password"
        self.check_has_command(cmd)

        if crypted:
            openssl_cmd = "openssl passwd -6 %s" % password
            password = process.run(openssl_cmd).stdout_text.strip('\n')

        args = {"crypted": crypted, "username": username,
                "password": base64.b64encode(password.encode()).decode()}
        return self.cmd(cmd=cmd, args=args)

    @error_context.context_aware
    def get_vcpus(self):
        """
        Get the vcpus information
        """
        cmd = "guest-get-vcpus"
        self.check_has_command(cmd)
        return self.cmd(cmd=cmd)

    @error_context.context_aware
    def set_vcpus(self, action):
        """
        Set the status of vcpus, bring up/down the vcpus following action
        """
        cmd = "guest-set-vcpus"
        self.check_has_command(cmd)
        return self.cmd(cmd=cmd, args=action)

    @error_context.context_aware
    def get_time(self):
        """
        Get the time of guest, return the time from Epoch of 1970-01-01 in UTC
        in nanoseconds
        """
        cmd = "guest-get-time"
        self.check_has_command(cmd)
        return self.cmd(cmd=cmd)

    @error_context.context_aware
    def set_time(self, nanoseconds=None):
        """
        set the time of guest, the params passed in is in nanoseconds
        """
        cmd = "guest-set-time"
        args = None
        self.check_has_command(cmd)
        if nanoseconds:
            args = {"time": nanoseconds}
        return self.cmd(cmd=cmd, args=args)

    @error_context.context_aware
    def guest_info(self):
        """
        Send "guest-info", return all supported cmds.
        """
        cmd = "guest-info"
        return self.cmd(cmd=cmd, debug=False)

    @error_context.context_aware
    def fstrim(self):
        """
        Discard unused blocks on a mounted filesystem by guest agent operation
        """
        cmd = "guest-fstrim"
        self.check_has_command(cmd)
        return self.cmd(cmd)

    @error_context.context_aware
    def get_network_interface(self):
        """
        Get the network interfaces of the guest by guest agent operation
        """
        cmd = "guest-network-get-interfaces"
        self.check_has_command(cmd)
        return self.cmd(cmd)

    @error_context.context_aware
    def suspend(self, mode=SUSPEND_MODE_RAM):
        """
        This function tries to execute the scripts provided by the pm-utils
        package via guest agent interface. If it's not available, the suspend
        operation will be performed by manually writing to a sysfs file.

        Notes:

        #. For the best results it's strongly recommended to have the
           ``pm-utils`` package installed in the guest.
        #. The ``ram`` and 'hybrid' mode require QEMU to support the
           ``system_wakeup`` command.  Thus, it's *required* to query QEMU
           for the presence of the ``system_wakeup`` command before issuing
           guest agent command.

        :param mode: Specify suspend mode, could be one of ``disk``, ``ram``,
                     ``hybrid``.
        :return: True if shutdown cmd is sent successfully, False if
                 ``suspend`` is unsupported.
        :raise VAgentSuspendUnknownModeError: Raise if mode is not supported.
        """
        error_context.context(
            "Suspend guest '%s' to '%s'" % (self.vm.name, mode))

        if mode not in [self.SUSPEND_MODE_DISK, self.SUSPEND_MODE_RAM,
                        self.SUSPEND_MODE_HYBRID]:
            raise VAgentSuspendUnknownModeError("Not supported suspend"
                                                " mode '%s'" % mode)

        cmd = "guest-suspend-%s" % mode
        self.check_has_command(cmd)

        # First, sync with guest.
        self.sync()

        # Then send suspend cmd.
        self.cmd(cmd=cmd, success_resp=False)

        return True

    def get_fsfreeze_status(self):
        """
        Get guest 'fsfreeze' status. The status could be 'frozen' or 'thawed'.
        """
        cmd = "guest-fsfreeze-status"
        if self.check_has_command(cmd):
            return self.cmd(cmd=cmd)

    def verify_fsfreeze_status(self, expected):
        """
        Verify the guest agent fsfreeze status is same as expected, if not,
        raise a VAgentFreezeStatusError.

        :param expected: The expected status.
        :raise VAgentFreezeStatusError: Raise if the guest fsfreeze status is
                unexpected.
        """
        status = self.get_fsfreeze_status()
        if status != expected:
            raise VAgentFreezeStatusError(self.vm.name, status, expected)

    @error_context.context_aware
    def fsfreeze(self, check_status=True, timeout=FSFREEZE_TIMEOUT,
                 fsfreeze_list=False, mountpoints=None):
        """
        Freeze File system on guest, there are two commands,
        "guest-fsfreeze-freeze" and "guest-fsfreeze-freeze-list".
        guest-fsfreeze-freeze: Sync and freeze all freezable,
        local guest filesystems.
        guest-fsfreeze-freeze-list: Sync and freeze specified guest
        filesystems

        :param check_status: Force this function to check the fsfreeze status
                             before/after sending cmd.
        :param fsfreeze_list: Bool value, if the value is True
                              assume guest-fsfreeze-freeze-list command,
                              else assume guest-fsfreeze-freeze command.
        :param mountpoints: an array of mountpoints of filesystems,
                            If omitted, every mounted filesystem is frozen.
        :return: Frozen FS number if cmd succeed, -1 if guest agent doesn't
                 support fsfreeze cmd.
        """
        error_context.context("Freeze FS in guest '%s'" % self.vm.name)
        if check_status:
            self.verify_fsfreeze_status(self.FSFREEZE_STATUS_THAWED)

        cmd = "guest-fsfreeze-freeze"
        args = None
        if fsfreeze_list:
            cmd = "guest-fsfreeze-freeze-list"
            if mountpoints:
                args = {"mountpoints": mountpoints}

        if self.check_has_command(cmd):
            ret = self.cmd(cmd=cmd, timeout=timeout, args=args)
            if check_status:
                try:
                    self.verify_fsfreeze_status(self.FSFREEZE_STATUS_FROZEN)
                # pylint: disable=E0712
                except VAgentFreezeStatusError:
                    # When the status is incorrect, reset fsfreeze status to
                    # 'thawed'.
                    self.cmd(cmd="guest-fsfreeze-thaw")
                    raise
            return ret
        return -1

    @error_context.context_aware
    def fsthaw(self, check_status=True):
        """
        Thaw File system on guest.

        :param check_status: Force this function to check the fsfreeze status
                             before/after sending cmd.
        :return: Thaw FS number if cmd succeed, -1 if guest agent doesn't
                 support fsfreeze cmd.
        """
        error_context.context("thaw all FS in guest '%s'" % self.vm.name)
        if check_status:
            self.verify_fsfreeze_status(self.FSFREEZE_STATUS_FROZEN)

        cmd = "guest-fsfreeze-thaw"
        if self.check_has_command(cmd):
            ret = self.cmd(cmd=cmd)
            if check_status:
                try:
                    self.verify_fsfreeze_status(self.FSFREEZE_STATUS_THAWED)
                # pylint: disable=E0712
                except VAgentFreezeStatusError:
                    # When the status is incorrect, reset fsfreeze status to
                    # 'thawed'.
                    self.cmd(cmd=cmd)
                    raise
            return ret
        return -1

    def _cmd_args_update(self, cmd, **kwargs):
        """
        Update qga commands' args.

        :param cmd: command to send.
        :param kwargs: optional keyword arguments.
        :return: The command's output.
        """
        self.check_has_command(cmd)
        # update kwargs
        for key in list(kwargs.keys()):
            if kwargs[key] is None:
                kwargs.pop(key)
                continue
            if "_" in key:
                key_new = key.replace("_", "-")
                args = {key_new: kwargs[key]}
                kwargs.pop(key)
                kwargs.update(args)

        return self.cmd(cmd=cmd, args=kwargs)

    def guest_file_open(self, path, mode=None):
        """
        Open a guest file.

        :param path: full path to the file in the guest to open.
        :param mode: optional open mode, "r" is the default value.
        :return: file handle.
        """
        cmd = "guest-file-open"
        return self._cmd_args_update(cmd, path=path, mode=mode)

    def guest_file_close(self, handle):
        """
        Close an opened guest file.

        :param handle: file handle returned by guest-file-open.
        :return: no-error return.
        """
        cmd = "guest-file-close"
        return self._cmd_args_update(cmd, handle=handle)

    def guest_file_write(self, handle, content, count=None):
        """
        Write to guest file.

        :param handle: file handle returned by guest-file-open.
        :param content: content to write.
        :param count: optional bytes to write (actual bytes, after
               base64-decode),default is all content in buf-b64 buffer
               after base64 decoding
        :return: a dict with count and eof.
        """
        cmd = "guest-file-write"
        con_encode = base64.b64encode(content.encode()).decode()
        return self._cmd_args_update(cmd, handle=handle,
                                     buf_b64=con_encode, count=count)

    def guest_file_read(self, handle, count=None):
        """
        Read guest file.

        :param handle: file handle returned by guest-file-open.
        :param count: optional,maximum number of bytes to read before
                      base64-encoding is applied(default is 4KB)
        :return: a dict with base64-encoded string content,count and eof.
        """
        cmd = "guest-file-read"
        return self._cmd_args_update(cmd, handle=handle, count=count)

    def guest_file_flush(self, handle):
        """
        Flush the write content to disk.

        :param handle: file handle returned by guest-file-open.
        :return: no-error return.
        """
        cmd = "guest-file-flush"
        return self._cmd_args_update(cmd, handle=handle)

    def guest_file_seek(self, handle, offset, whence):
        """
        Seek the position of guest file.

        :param handle: filehandle returned by guest-file-open.
        :param offset: offset of whence.
        :param whence: 0,file beginning;
                       1,file current position;
                       2,file end
        :return: a dict with position and eof.
        """
        cmd = "guest-file-seek"
        return self._cmd_args_update(cmd, handle=handle, offset=offset,
                                     whence=whence)

    def guest_exec(self, path, arg=None, env=None, input_data=None,
                   capture_output=None):
        """
        Execute a command in the guest.

        :param path: path or executable name to execute
        :param arg: argument list to pass to executable
        :param env: environment variables to pass to executable
        :param input_data: data to be passed to process stdin (base64 encoded)
        :param capture_output: bool flag to enable capture of stdout/stderr of
                               running process,defaults to false.
        :return: PID on success
        """
        cmd = "guest-exec"
        return self._cmd_args_update(cmd, path=path, arg=arg, env=env,
                                     input_data=input_data,
                                     capture_output=capture_output)

    def guest_exec_status(self, pid):
        """
        Check status of process associated with PID retrieved via guest-exec.
        Read the process and associated metadata if it has exited.

        :param pid: pid returned from guest-exec
        :return: GuestExecStatus on success,
                 such as exited,exitcode,out-data,error-data and so on
        """
        cmd = "guest-exec-status"
        return self._cmd_args_update(cmd, pid=pid)

    def get_disks(self):
        """
        Send "guest-get-disks", return disks info of guest.
        """
        cmd = "guest-get-disks"
        self.check_has_command(cmd)
        return self.cmd(cmd)

    def ssh_add_authorized_keys(self, username, *keys, **kwargs):
        """
        Add ssh public keys into guest-agent.

        :param username: username of host
        :param keys: value of public keys
        :param kwargs: optional keyword arguments
        :return: command handle
        """
        cmd = "guest-ssh-add-authorized-keys"
        keys = list(keys)
        reset = kwargs.get('reset')
        return self._cmd_args_update(cmd, username=username,
                                     keys=keys, reset=reset)

    def ssh_remove_authorized_keys(self, username, *keys):
        """
        Remove ssh public keys from guest-agent.

        :param username: usrename of host
        :param keys: value of public keys
        :return: command handle
        """
        cmd = "guest-ssh-remove-authorized-keys"
        keys = list(keys)
        return self._cmd_args_update(cmd, username=username, keys=keys)

    def ssh_get_authorized_keys(self, username):
        """
        Get ssh public keys from guest-agent.

        :param username: usrename of host
        :return: command handle
        """
        cmd = "guest-ssh-get-authorized-keys"
        return self._cmd_args_update(cmd, username=username)

    def get_fsinfo(self):
        """
        Send "guest-get-fsinfo", return file system info of guest.
        """
        cmd = "guest-get-fsinfo"
        self.check_has_command(cmd)
        return self.cmd(cmd)

    def get_osinfo(self):
        """
        Send "guest-get-osinfo", return operating system info of guest.
        """
        cmd = "guest-get-osinfo"
        self.check_has_command(cmd)
        return self.cmd(cmd)

    def get_memory_block_info(self):
        """
        Get information relating to guest memory blocks.
        """
        cmd = "guest-get-memory-block-info"
        self.check_has_command(cmd)
        return self.cmd(cmd=cmd)

    def get_memory_blocks(self):
        """
        Get the list of the guest's memory blocks.
        """
        cmd = "guest-get-memory-blocks"
        self.check_has_command(cmd)
        return self.cmd(cmd=cmd)

    def set_memory_blocks(self, mem_blocks_list):
        """
        Reconfigure (currently: enable/disable) state of guest memory blocks.

        :param mem_blocks_list: a list of memory blocks the guest knows about
        :return: a list of memory blocks response, which is corresponding
                 to the input list
        """
        cmd = "guest-set-memory-blocks"
        return self._cmd_args_update(cmd, mem_blks=mem_blocks_list)

    def get_host_name(self):
        """
        Get host name of vm.
        """
        cmd = "guest-get-host-name"
        self.check_has_command(cmd)
        return self.cmd(cmd=cmd)

    def get_timezone(self):
        """
        Get time zone of vm.
        :return: a timezone dict includes name and an offset to UTC in seconds.
        """
        cmd = "guest-get-timezone"
        self.check_has_command(cmd)
        return self.cmd(cmd=cmd)

    def get_users(self):
        """
        Get currently active users on the vm.
        :return: a list of currently active users, includes user name, login
                 time and domain(windows only).
        """
        cmd = "guest-get-users"
        self.check_has_command(cmd)
        return self.cmd(cmd=cmd)

    def get_virtio_device(self):
        """
        Get virtio device driver info of windows guest.

        :return: a list of virtio device driver info, such as device-id,
                 driver-name, driver-version, driver-date and vender-id.
        """
        cmd = "guest-get-devices"
        self.check_has_command(cmd)
        return self.cmd(cmd=cmd)
