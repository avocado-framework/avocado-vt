from __future__ import division

import array
import json
import logging
import re
import select
import socket
import threading
import time

import six
from virttest import utils_misc

from . import errors

LOG = logging.getLogger("avocado." + __name__)


class Monitor(object):

    """
    Common code for monitor classes.
    """

    ACQUIRE_LOCK_TIMEOUT = 20
    DATA_AVAILABLE_TIMEOUT = 0
    CONNECT_TIMEOUT = 60

    def __init__(
        self, instance_id, name, type, address, log_file, suppress_exceptions=False
    ):
        """
        Initialize the instance.

        """
        self.instance_id = instance_id
        self.name = name
        self.type = type
        self.address = address
        self._lock = threading.RLock()
        self._log_lock = threading.RLock()
        self._log_file = log_file
        self._open_log_files = {}

        if type == "tcp_socket":
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.CONNECT_TIMEOUT)
            self._socket.connect(*address)
        elif type == "unix_socket":
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.settimeout(self.CONNECT_TIMEOUT)
            self._socket.connect(address)
        else:
            raise NotImplementedError("Do not support the type %s." % type)
        self._server_closed = False

    def __del__(self):
        # Automatically close the connection when the instance is garbage
        # collected
        self._close_sock()
        if not self._acquire_lock(lock=self._log_lock):
            raise BlockingIOError(
                "Could not acquire exclusive lock to access"
                " %s " % self._open_log_files
            )
        try:
            del_logs = []
            for log in self._open_log_files:
                self._open_log_files[log].close()
                del_logs.append(log)
            for log in del_logs:
                self._open_log_files.pop(log)
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
        return (
            self.instance_id,
            self.name,
            self.type,
            self.address,
            self._log_file,
            True,
        )

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
        except ValueError:
            pass
        except socket.error as e:
            raise errors.MonitorSocketError("Verifying data on monitor socket", e)

    def _recvall(self):
        """
        Receive bytes from socket.recv().

        return s type: bytes
        """
        s = b""
        while self._data_available():
            data = self._socket.recv(1024)
            if not data:
                self._server_closed = True
                break
            s += data
        return s

    def _log_lines(self, log_str):
        """
        Record monitor cmd/output in log file.
        """
        if not self._acquire_lock(lock=self._log_lock):
            raise BlockingIOError(
                "Could not acquire exclusive lock to access"
                " %s" % self._open_log_files
            )
        try:
            log = self._log_file
            timestr = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                if self._log_file not in self._open_log_files:
                    self._open_log_files[log] = open(log, "a")
                for line in log_str.splitlines():
                    self._open_log_files[log].write("%s: %s\n" % (timestr, line))
                self._open_log_files[log].flush()
            except Exception as err:
                txt = "Fail to record log to %s.\n" % log
                txt += "Log content: %s\n" % log_str
                txt += "Exception error: %s" % err
                LOG.error(txt)
                self._open_log_files[log].close()
                self._open_log_files.pop(log)
        finally:
            self._log_lock.release()

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
        except errors.MonitorError:
            return False

    def close(self):
        """
        Close the connection to the monitor and its log file.
        """
        self._close_sock()
        if not self._acquire_lock(lock=self._log_lock):
            raise BlockingIOError(
                "Could not acquire exclusive lock to access"
                " %s" % self._open_log_files
            )
        try:
            del_logs = []
            for log in self._open_log_files:
                self._open_log_files[log].close()
                del_logs.append(log)
            for log in del_logs:
                self._open_log_files.pop(log)
        finally:
            self._log_lock.release()


class HumanMonitor(Monitor):
    """
    Wraps QMP monitor commands.
    """

    READ_OBJECTS_TIMEOUT = 10
    CMD_TIMEOUT = 900
    RESPONSE_TIMEOUT = 600
    PROMPT_TIMEOUT = 90

    def __init__(self, name, type, address, log_file, suppress_exceptions=False):
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
            super(HumanMonitor, self).__init__(name, type, address, log_file)

            self.protocol = "human"

            # # Find the initial (qemu) prompt
            # s, o = self._read_up_to_qemu_prompt()
            # if not s:
            #     raise errors.MonitorProtocolError(
            #         "Could not find (qemu) prompt "
            #         "after connecting to monitor. "
            #         "Output so far: %r" % o
            #     )
            #
            # self._get_supported_cmds()

        except errors.MonitorError as e:
            self._close_sock()
            if suppress_exceptions:
                LOG.warn(e)
            else:
                raise


class QMPMonitor(Monitor):
    """
    Wraps QMP monitor commands.
    """

    READ_OBJECTS_TIMEOUT = 10
    CMD_TIMEOUT = 900
    RESPONSE_TIMEOUT = 600
    PROMPT_TIMEOUT = 90

    def __init__(
        self, instance_id, name, type, address, log_file, suppress_exceptions=False
    ):
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
            super(QMPMonitor, self).__init__(instance_id, name, type, address, log_file)

            self.protocol = "qmp"
            self._greeting = None
            self._events = []
            self._supported_hmp_cmds = []
            self._supported_cmds = []

            # Make sure json is available
            try:
                json
            except NameError:
                raise errors.MonitorNotSupportedError(
                    "QMP requires the json module " "(Python 2.6 and up)"
                )

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
                raise errors.MonitorProtocolError(
                    "%s: No QMP greeting message received."
                    " Output so far: %s" % (name, output_str)
                )

            # Issue qmp_capabilities
            self.cmd("qmp_capabilities")

            self._get_supported_cmds()

        except errors.MonitorError as e:
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

    def _send(self, data, fds=None):
        """
        Send raw bytes data without waiting for response.

        :param data: Data to send
        :type data: bytes
        :param fds: File descriptors to send, if any
        :type fds: list[int] | None
        :raise MonitorSocketError: Raised if a socket error occurs
        """
        func = self._socket.sendall
        args = [data + b"\n"]
        if fds:
            func = self._socket.sendmsg
            args = [
                args,
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))],
            ]
        try:
            func(*args)
            self._log_lines(data.decode(errors="replace"))
        except socket.error as e:
            raise errors.MonitorSocketError("Could not send data: %r" % data, e)

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
            self._supported_cmds = [n["name"] for n in cmds if "name" in n]

        if not self._supported_cmds:
            LOG.warn("Could not get supported monitor cmds list")

    def _get_supported_hmp_cmds(self):
        """
        Get supported human monitor cmds list.
        """
        cmds = self.human_monitor_cmd("help", debug=False)
        if cmds:
            cmd_list = re.findall(r"(?:^\w+\|(\w+)\s)|(?:^(\w+?)\s)", cmds, re.M)
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
            raise errors.MonitorNotSupportedCmdError(self.name, cmd)

    def _log_response(self, cmd, resp, debug=True):
        """
        Print log message for monitor cmd's response.

        :param cmd: Command string.
        :param resp: Response from monitor command.
        :param debug: Whether to print the commands.
        """

        def _log_output(o, indent=0):
            LOG.debug(
                "(monitor %s.%s) =   %s%s", self.instance_id, self.name, " " * indent, o
            )

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

        if debug:
            LOG.debug(
                "(monitor %s.%s) Response to '%s' " "(re-formatted)",
                self.instance_id,
                self.name,
                cmd,
            )
            if isinstance(resp, dict):
                _dump_dict(resp)
            elif isinstance(resp, list):
                _dump_list(resp)
            else:
                for l in str(resp).splitlines():
                    _log_output(l)

    def execute_data(self, data, timeout=None, debug=False, fd=None, data_format=None):
        if data_format == "cmd":
            cmd, args = data
            return self.cmd(cmd, args, timeout, debug, fd)

        elif data_format == "raw":
            return self.cmd_raw(data, timeout)

        elif data_format == "obj":
            return self.cmd_obj(data, timeout)

        elif data_format == "qmp":
            return self.cmd_qmp(data, timeout)

        else:
            raise errors.MonitorProtocolError("Unknown data format: %s" % data_format)

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
        if not self._acquire_lock():
            raise errors.MonitorLockError(
                "Could not acquire exclusive lock to send " "QMP command '%s'" % cmd
            )

        try:
            # Read any data that might be available
            self._read_objects()
            # Send command
            q_id = utils_misc.generate_random_string(8)
            cmdobj = json.dumps(self._build_cmd(cmd, args, q_id))
            msg = cmdobj.encode()
            fds = (
                [fd.fileno() if not isinstance(fd, int) else fd]
                if fd is not None
                else None
            )

            if debug:
                LOG.debug("Send command: %s" % cmdobj)
            self._send(msg, fds)
            # Read response
            r = self._get_response(q_id, timeout)
            if r is None:
                raise errors.MonitorProtocolError(
                    "Received no response to QMP "
                    "command '%s', or received a "
                    "response with an incorrect id" % cmd
                )
            if "return" in r:
                ret = r["return"]
                if ret:
                    self._log_response(cmd, ret, debug)
                return ret
            if "error" in r:
                raise errors.QMPCmdError(cmd, args, r["error"])

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
            raise errors.MonitorLockError(
                "Could not acquire exclusive lock to send " "data: %r" % data
            )

        try:
            self._read_objects()
            self._send(data.encode())
            r = self._get_response(None, timeout)
            if r is None:
                raise errors.MonitorProtocolError(
                    "Received no response to data: %r" % data
                )
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

    def get_events(self):
        """
        Return a list of the asynchronous events received since the last
        clear_events() call.

        :return: A list of events (the objects returned have an "event" key)
        :raise MonitorLockError: Raised if the lock cannot be acquired
        """
        if not self._acquire_lock():
            raise errors.MonitorLockError(
                "Could not acquire exclusive lock to read " "QMP events"
            )
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

    def clear_events(self):
        """
        Clear the list of asynchronous events.

        :raise MonitorLockError: Raised if the lock cannot be acquired
        """
        if not self._acquire_lock():
            raise errors.MonitorLockError(
                "Could not acquire exclusive lock to clear " "QMP event list"
            )
        self._events = []
        self._lock.release()

    def clear_event(self, name):
        """
        Clear a kinds of events in events list only.

        :raise MonitorLockError: Raised if the lock cannot be acquired
        """
        if not self._acquire_lock():
            raise errors.MonitorLockError(
                "Could not acquire exclusive lock to clear " "QMP event list"
            )
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

    def verify_responsive(self):
        """
        Make sure the monitor is responsive by sending a command.
        """
        self.cmd(cmd="query-status", debug=False)

    def verify_status(self, status):
        """
        Verify VM status

        :param status: Optional VM status, 'running' or 'paused'
        :return: return True if VM status is same as we expected
        """
        o = dict(self.cmd(cmd="query-status", debug=False))
        if status == "paused":
            return o["running"] is False
        if status == "running":
            return o["running"] is True
        if o["status"] == status:
            return True
        return False

    def get_status(self):
        """
        Get VM status.

        :return: return VM status
        """
        return self.cmd(cmd="query-status", debug=False)

    def quit(self):
        """
        Send "quit" and return the response.
        """
        return self.cmd("quit")

    def _has_command(self, cmd):
        """
        Check whether kvm monitor support 'cmd'.

        :param cmd: command string which will be checked.

        :return: True if cmd is supported, False if not supported.
        """
        if cmd and cmd in self._supported_cmds:
            return True
        return False

    def human_monitor_cmd(self, cmd="", timeout=CMD_TIMEOUT, debug=True, fd=None):
        """
        Run human monitor command in QMP through human-monitor-command

        :param cmd: human monitor command.
        :param timeout: Time duration to wait for response
        :param debug: Whether to print the commands being sent and responses
        :param fd: file object or file descriptor to pass

        :return: The response to the command
        """
        args = {"command-line": cmd}
        ret = self.cmd("human-monitor-command", args, timeout, False, fd)

        if ret:
            self._log_response(cmd, ret, debug)
        return ret

    def info(self, what, debug=True):
        """
        Request info about something and return the response.
        """
        cmd = "query-%s" % what
        if not self._has_command(cmd):
            cmd = "info %s" % what
            return self.human_monitor_cmd(cmd, debug=debug)

        return self.cmd(cmd, debug=debug)
