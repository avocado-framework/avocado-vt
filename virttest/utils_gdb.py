import os
import logging
import signal
import threading
try:
    import queue as Queue
except ImportError:
    import Queue

import aexpect

from enum import Enum
from virttest import utils_misc


class GDBError(Exception):

    """
    General module exception class
    """

    pass


class GDBCmdError(GDBError):

    """
    Exception raised when calling an gdb command.
    """

    def __init__(self, command, msg):
        self.command = command
        self.msg = msg

    def __str__(self):
        return 'Error when calling GDB command %s:\n%s' % (
            self.command, self.msg)


def _split_result_str(result_str):
    """
    Helper function to split a string into a list of
    (key, value) tuples while minding braces matching.
    """
    result = []
    key = ''
    value = ''
    current = 'key'
    braces = []
    for ch in result_str:
        if ch == '=' and not braces:
            if current == 'key':
                current = 'value'
        elif ch == ',' and not braces:
            result.append((key, value))
            key = ''
            value = ''
            if current == 'value':
                current = 'key'
        else:
            if ch in ['{', '[']:
                braces.append(ch)
            elif ch == ']':
                if braces[-1] == '[':
                    braces.pop()
            elif ch == '}':
                if braces[-1] == '{':
                    braces.pop()

            if current == 'key':
                key += ch
            elif current == 'value':
                value += ch

    if not braces:
        result.append((key, value))
    return result


def _parse_result(result_str):
    """
    Helper function to parse a GDB/MI result string into Python
    friendly data collections like lists and dicts.
    """
    if result_str.startswith('"') and result_str.endswith('"'):
        return result_str[1:-1]

    result = {}
    if result_str.startswith('[') and result_str.endswith(']'):
        result_str = result_str[1:-1]
        result = []
    elif result_str.startswith('{') and result_str.endswith('}'):
        result_str = result_str[1:-1]

    if not result_str:
        return result

    for key, value_str in _split_result_str(result_str):
        value = _parse_result(value_str)
        if type(result) == list:
            result.append((key, value))
        elif type(result) == dict:
            result[key] = value

    return result


class GDB(aexpect.Expect):

    """
    Class to manipulate a inferior process in gdb.
    """

    def __init__(self, command=None):
        self.running = False
        self.terminated = False
        self.exiting = False
        self.cmd_lock = threading.Lock()
        self.inferior_command = command

        self.output_queue = Queue.Queue()
        self.cmd_queue = Queue.Queue()
        self.cmd_result_queue = Queue.Queue()

        self.notify_async_output = []
        self.exec_async_output = []
        self.status_async_output = []
        self.log_stream = []
        self.console_stream = []
        self.target_stream = []
        self.callback_threads = []
        self.prompt = '(gdb)'
        self.pid = None

        dummy_cb = (lambda self, info, params: None, None)
        self.callbacks = {
            "stop": dummy_cb,
            "start": dummy_cb,
            "termination": dummy_cb,
            "break": dummy_cb,
            "signal": dummy_cb,
        }

        self.thread_groups = {}

        command = 'gdb --quiet --interpreter=mi %s' % command
        aexpect.Expect.__init__(
            self,
            command=command,
        )
        self.log_polling_thread = threading.Thread(target=self._poll_log)
        self.log_polling_thread.start()
        self._read_output_until_prompt(timeout=3)

    def _parse_notify_async_line(self, line):
        """
        Parse a GDB/MI async notify line and change state accordingly.

        :param line: GDB/MI line to be parsed.
        """
        event, info_str = line.lstrip('=').split(',', 1)
        info = _parse_result(info_str)
        if event == 'thread-group-added':
            self.thread_groups[info['id']] = {
                'status': 'stopped',
                'pid': None,
                'threads': set()
            }
            self.current_thread_group = info['id']
        elif event == 'thread-group-started':
            pid = int(info['pid'])
            t_group = self.thread_groups[info['id']]
            t_group['status'] = 'running'
            t_group['pid'] = self.pid = pid
        elif event == 'thread-group-exited':
            t_group = self.thread_groups[info['id']]
            t_group['status'] = 'stopped'
            t_group['pid'] = self.pid = None
        elif event == 'thread-created':
            t_group = self.thread_groups[info['group-id']]
            t_id = int(info['id'])
            t_group['threads'].add(t_id)
        elif event == 'thread-exited':
            t_group = self.thread_groups[info['group-id']]
            t_id = int(info['id'])
            t_group['threads'].remove(t_id)
        elif event in ['library-loaded', 'library-unloaded']:
            pass
        else:
            logging.warning('Unprocessed gdb async notification:\n%s', line)

    def _parse_exec_async_line(self, line):
        """
        Parse a GDB/MI async exec line and change state accordingly.

        :param line: GDB/MI line to be parsed.
        """
        event, info_str = line.split(',', 1)
        info = _parse_result(info_str)
        if event == '*stopped':
            self.running = False
            self._callback('stop', info)
            if info:
                if 'reason' in info:
                    if info['reason'] == 'breakpoint-hit':
                        self._callback('break', info)
                    if info['reason'] == 'signal-received':
                        self._callback('signal', info)
                    if info['reason'] in ['exited', 'exited-normally',
                                          'exited-signalled']:
                        self.terminated = True
                        self._callback('termination', info)
                else:
                    for key in info:
                        logging.warning('Stopped without reason')
                        logging.warning('%s: %s', key, info[key])
            else:
                self._callback('termination', info)
        if event == '*running':
            if not self.running:
                self.running = True
                self._callback('start', info)

    def _parse_status_async_line(self, line):
        """
        Parse a GDB/MI async status line and change state accordingly.

        :param line: GDB/MI line to be parsed.
        """
        pass

    def _parse_cmd_result_line(self, line):
        """
        Parse a GDB/MI command result line and change state accordingly.

        :param line: GDB/MI line to be parsed.
        """
        command = self.cmd_queue.get()
        result = {'command': command}
        res = line.lstrip('^').split(',', 1)
        result['status'] = res[0]
        if len(res) == 2:
            result['info'] = _parse_result(res[1])
        elif len(res) == 1:
            result['info'] = {}
        self.cmd_result_queue.put(result)

    def _read_output_until_prompt(self, timeout=300):
        """
        Read GDB/MI output until a command prompt reached.

        :param timeout: Max time for the reading.
        """
        result = []
        while True:
            line = self.output_queue.get(timeout=timeout)
            result.append(line)
            if line.startswith('(gdb)'):
                return result

    def _poll_log(self):
        """
        Read GDB/MI output continuously and parse lines according to its
        inital until `exit` variable is set.
        """
        while True:
            res = self.read_nonblocking()
            if res.strip():
                for line in res.splitlines():
                    if line.startswith('='):
                        self._parse_notify_async_line(line)
                    elif line.startswith('*'):
                        self._parse_exec_async_line(line)
                    elif line.startswith('+'):
                        self._parse_status_async_line(line)
                    elif line.startswith('^'):
                        self._parse_cmd_result_line(line)
                    else:
                        self.output_queue.put(line)
            if self.exiting:
                break

    def _callback(self, callback_type, info):
        """
        General callback function to call specific type of callback funtions.

        :param callback_type: Could be one of "stop", "start", "termination",
                              "break" or "signal"
        """
        callback_func, params = self.callbacks[callback_type]
        logging.debug('gdb is Calling back %s' % callback_type)
        thread = threading.Thread(
            target=callback_func,
            args=(self, info, params),
            name=callback_type
        )
        thread.start()
        self.callback_threads.append(thread)

    def set_callback(self, callback_type, func, params=None):
        """
        Set a callback function to a customized function.

        :param callback_type: Could be one of "stop", "start", "termination",
                              "break" or "signal"
        :param func: Function to be set as callback
        :param params: Parameters to be passed to callback function
        """
        self.callbacks[callback_type] = (func, params)

    def stop(self):
        """
        Stop inferior by sending a SIGINT signal.
        """
        if self.running:
            self.send_signal('SIGINT')
            self.wait_for_stop()

    def kill(self):
        """
        Kill inferior by sending a SIGTERM signal.
        """
        def temp_callback(gdb, info, params):
            if info['signal-name'] == 'SIGTERM':
                self.cont()

        if self.running:
            stop_cb, stop_cb_params = self.callbacks['signal']
            self.set_callback('signal', temp_callback)
            self.send_signal('SIGTERM')
            self.wait_for_termination()
            self.set_callback('signal', stop_cb, stop_cb_params)

    def cont(self):
        """
        Continue a stopped inferior.
        """
        self.cmd('-exec-continue')
        if not self.running and not self.terminated:
            self.wait_for_start()

    def insert_break(self, break_func):
        """
        Insert a function breakpoint.

        :param break_func: Function at which breakpoint inserted
        """
        return self.cmd('-break-insert -f %s' % break_func)

    def back_trace(self):
        """
        Get current backtrace stack as a list of lines.
        """
        result = self.cmd('-stack-list-frames')

        bts = []
        for line in result['info']['stack']:
            bt = line[1]
            bt_line = "#%2s" % bt['level']
            if 'addr' in bt:
                bt_line += " %s" % bt['addr']
            if 'func' in bt:
                bt_line += " %-30s" % bt['func']
            if 'fullname' in bt:
                bt_line += " %s:%s" % (bt['fullname'], bt['line'])
            elif 'from' in bt:
                bt_line += " %s" % bt['from']
            bts.append(bt_line)
        return bts

    def run(self, arg_str=''):
        """
        Start the inferior with an optional argument string.

        :param arg_str: Argument the inferior to be called with
        """
        if not self.running:
            cmd_line = '-exec-run ' + arg_str
            result = self.cmd(cmd_line)
            self.wait_for_start()
            self.terminated = False
            return result

    def send_signal(self, signal_name):
        """
        Send a signal to the inferior.

        :param signal_name: Signal name as a string or integer
        """
        if isinstance(signal_name, str):
            signal_name = getattr(signal, signal_name)

        if isinstance(signal_name, Enum):
            signal_name = signal_name.value

        if isinstance(signal_name, int):
            os.kill(self.pid, signal_name)
        else:
            raise ValueError("Signal should be a string or an integer.")

    def cmd(self, command, cont=True):
        """
        Call a gdb of GDB/MI command.

        :param command: Command line to be called
        :param cont: Whether continue the inferior after calling the command
        """
        was_running = False
        self.cmd_lock.acquire()
        try:
            if self.running:
                was_running = True
                self.stop()
            self.cmd_queue.put(command)
            self.sendline(command)
            result = self.cmd_result_queue.get()
            if result['command'] != command:
                raise GDBCmdError('Mismatch command result line got %s but '
                                  'expecting %s' %
                                  (result['command'], command))
            if result['status'] == 'exit':
                self.exiting = True
            elif result['status'] == 'error':
                raise GDBCmdError(command, result['info']['msg'])
            elif result['status'] == 'running':
                pass
            elif result['status'] == 'connected':
                pass
        finally:
            self.cmd_lock.release()
            if was_running and cont:
                self.cont()
        return result

    def wait_for_start(self, timeout=60):
        """
        Wait the inferior to start.

        :param timeout: Max time to wait
        """
        logging.debug("Waiting for gdb inferior %s to start"
                      % self.inferior_command)
        return utils_misc.wait_for(
            lambda: self.running,
            timeout,
            step=0.1,
        )

    def wait_for_stop(self, timeout=60):
        """
        Wait the inferior to be stopped.

        :param timeout: Max time to wait
        """
        logging.debug("Waiting for gdb inferior %s to stop"
                      % self.inferior_command)
        res = utils_misc.wait_for(
            lambda: not self.running,
            timeout,
            step=0.1,
        )
        return res

    def wait_for_termination(self, timeout=60):
        """
        Wait the gdb session to be exited.

        :param timeout: Max time to wait
        """
        logging.debug("Waiting for gdb to terminate")
        return utils_misc.wait_for(
            lambda: self.terminated,
            timeout,
            step=0.1,
        )

    def exit(self):
        """
        Exit the gdb session.
        """
        self.cmd('-gdb-exit', cont=False)
        self.log_polling_thread.join()
        for thread in self.callback_threads:
            thread.join()
