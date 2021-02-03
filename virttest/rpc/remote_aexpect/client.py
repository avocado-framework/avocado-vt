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

"""
API used to run/control interactive processes.

:copyright: 2008-2015 Red Hat Inc.
"""

# disable too-many-* as we need them pylint: disable=R0902,R0913,R0914,C0302

import time
import signal
import os
import re
import threading
import shutil
import select
import subprocess
import locale
import logging

import remote_aexpect as aexpect

from aexpect.exceptions import ExpectError
from aexpect.exceptions import ExpectProcessTerminatedError
from aexpect.exceptions import ExpectTimeoutError
from aexpect.exceptions import ShellCmdError
from aexpect.exceptions import ShellError
from aexpect.exceptions import ShellProcessTerminatedError
from aexpect.exceptions import ShellStatusError
from aexpect.exceptions import ShellTimeoutError

from aexpect.shared import BASE_DIR
from aexpect.shared import get_filenames
from aexpect.shared import get_reader_filename
from aexpect.shared import get_lock_fd
from aexpect.shared import is_file_locked
from aexpect.shared import unlock_fd
from aexpect.shared import wait_for_lock

from aexpect.utils import astring
from aexpect.utils import data_factory
from aexpect.utils import genio
from aexpect.utils import process as utils_process
from aexpect.utils import path as utils_path
from aexpect.utils import wait as utils_wait


_THREAD_KILL_REQUESTED = threading.Event()


def kill_tail_threads():
    """
    Kill all Tail threads.

    After calling this function no new threads should be started.
    """
    _THREAD_KILL_REQUESTED.set()

    for thread in threading.enumerate():
        if hasattr(thread, "name") and thread.name.startswith("tail_thread"):
            thread.join(10)
    _THREAD_KILL_REQUESTED.clear()


class Spawn(object):

    """
    This class is used for spawning and controlling a child process.

    A new instance of this class can either run a new server (a small Python
    program that reads output from the child process and reports it to the
    client and to a text file) or attach to an already running server.

    When a server is started it runs the child process.

    The server writes output from the child's STDOUT and STDERR to a text file.
    The text file can be accessed at any time using get_output().
    In addition, the server opens as many pipes as requested by the client and
    writes the output to them.

    The pipes are requested and accessed by classes derived from Spawn.
    These pipes are referred to as "readers".
    The server also receives input from the client and sends it to the child
    process.

    An instance of this class can be pickled.  Every derived class is
    responsible for restoring its own state by properly defining
    __getinitargs__().

    The first named pipe is used by _tail(), a function that runs in the
    background and reports new output from the child as it is produced.
    The second named pipe is used by a set of functions that read and parse
    output as requested by the user in an interactive manner, similar to
    pexpect.

    When unpickled it automatically
    resumes _tail() if needed.
    """

    def __init__(self, command=None, a_id=None, auto_close=False, echo=False,
                 linesep="\n", pass_fds=(), encoding=None):
        """
        Initialize the class and run command as a child process.

        :param command: Command to run, or None if accessing an already running
                server.
        :param a_id: ID of an already running server, if accessing a running
                server, or None if starting a new one.
        :param auto_close: If True, close() the instance automatically when its
                reference count drops to zero (default False).
        :param echo: Boolean indicating whether echo should be initially
                enabled for the pseudo terminal running the subprocess.  This
                parameter has an effect only when starting a new server.
        :param linesep: Line separator to be appended to strings sent to the
                child process by sendline().
        :param pass_fds: Optional sequence of file descriptors to keep open
                between the parent and child.
        :param encoding: Override text encoding (by default: autodetect by
                locale.getpreferredencoding())
        """
        self.a_id = a_id or data_factory.generate_random_string(8)
        self.log_file = None
        self.closed = False
        if encoding is None:
            self.encoding = locale.getpreferredencoding()
            if self.encoding is None:
                self.encoding = "UTF-8"
        else:
            self.encoding = encoding
        self.reader_fds = {}
        base_dir = os.path.join(BASE_DIR, 'aexpect_%s' % self.a_id)

        # Define filenames for communication with server
        utils_path.init_dir(base_dir)

        (self.shell_pid_filename,
         self.status_filename,
         self.output_filename,
         self.inpipe_filename,
         self.ctrlpipe_filename,
         self.lock_server_running_filename,
         self.lock_client_starting_filename,
         self.server_log_filename) = get_filenames(base_dir)

        assert os.path.isdir(base_dir)

        self.command = command

        # Remember some attributes
        self.auto_close = auto_close
        self.echo = echo
        self.linesep = linesep

        # Make sure the 'readers' and 'close_hooks' attributes exist
        if not hasattr(self, "readers"):
            self.readers = []
        if not hasattr(self, "close_hooks"):
            self.close_hooks = []

        # Define the reader filenames
        self.reader_filenames = dict(
            (reader, get_reader_filename(base_dir, reader))
            for reader in self.readers)

        # Let the server know a client intends to open some pipes;
        # if the executed command terminates quickly, the server will wait for
        # the client to release the lock before exiting
        lock_client_starting = get_lock_fd(self.lock_client_starting_filename)

        # Start the server (which runs the command)
        if command:
            helper_cmd = utils_path.find_command('aexpect_helper')
            sub = subprocess.Popen([helper_cmd],
                                   shell=True,
                                   stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   pass_fds=pass_fds)
            # Send parameters to the server
            sub.stdin.write(("%s\n" % self.a_id).encode(self.encoding))
            sub.stdin.write(("%s\n" % echo).encode(self.encoding))
            readers = "%s\n" % ",".join(self.readers)
            sub.stdin.write(readers.encode(self.encoding))
            sub.stdin.write(("%s\n" % command).encode(self.encoding))
            sub.stdin.flush()
            # Wait for the server to complete its initialization
            while ("Server %s ready" % self.a_id not in
                   sub.stdout.readline().decode(self.encoding, "ignore")):
                pass

        # Open the reading pipes
        try:
            assert is_file_locked(self.lock_server_running_filename)
            for reader, filename in self.reader_filenames.items():
                self.reader_fds[reader] = os.open(filename, os.O_RDONLY)
        except (AssertionError, OSError):
            pass

        # Allow the server to continue
        unlock_fd(lock_client_starting)

    # The following two functions are defined to make sure the state is set
    # exclusively by the constructor call as specified in __getinitargs__().
    def __reduce__(self):
        return self.__class__, (self.__getinitargs__())

    def __getstate__(self):
        pass

    def __setstate__(self, state):
        pass

    def __getinitargs__(self):
        # Save some information when pickling -- will be passed to the
        # constructor upon unpickling
        return None, self.a_id, self.auto_close, self.echo, self.linesep

    def __del__(self):
        self._close_reader_fds()
        if self.auto_close:
            self.close()

    def _add_reader(self, reader):
        """
        Add a reader whose file descriptor can be obtained with _get_fd().

        Should be called before __init__().  Intended for use by derived
        classes.

        :param reader: The name of the reader.
        """
        if not hasattr(self, "readers"):
            self.readers = []
        self.readers.append(reader)

    def _add_close_hook(self, hook):
        """
        Add a close hook function to be called when close() is called.

        The function will be called after the process terminates but before
        final cleanup.  Intended for use by derived classes.

        :param hook: The hook function.
        """
        if not hasattr(self, "close_hooks"):
            self.close_hooks = []
        self.close_hooks.append(hook)

    def _get_fd(self, reader):
        """
        Return an open file descriptor corresponding to the specified reader
        pipe.  If no such reader exists, or the pipe could not be opened,
        return None.  Intended for use by derived classes.

        :param reader: The name of the reader.
        """
        return self.reader_fds.get(reader)

    def _close_reader_fds(self):
        """
        Close all reader file descriptors.
        """
        for fd_reader in self.reader_fds.values():
            try:
                os.close(fd_reader)
            except OSError:
                pass

    def get_id(self):
        """
        Return the instance's a_id attribute, which may be used to access the
        process in the future.
        """
        return self.a_id

    def get_pid(self):
        """
        Return the PID of the process.

        Note: this may be the PID of the shell process running the user given
        command.
        """
        try:
            with open(self.shell_pid_filename, 'r') as pid_file:
                try:
                    return int(pid_file.read())
                except ValueError:
                    return None
        except IOError:
            return None

    def get_status(self):
        """
        Wait for the process to exit and return its exit status, or None
        if the exit status is not available.
        """
        wait_for_lock(self.lock_server_running_filename)
        try:
            with open(self.status_filename, 'r') as status_file:
                try:
                    return int(status_file.read())
                except ValueError:
                    return None
        except IOError:
            return None

    def get_output(self):
        """
        Return the STDOUT and STDERR output of the process so far.
        """
        try:
            with open(self.output_filename, 'rb') as output_file:
                return output_file.read().decode(self.encoding,
                                                 'backslashreplace')
        except IOError:
            return None

    def get_stripped_output(self):
        """
        Return the STDOUT and STDERR output without the console codes escape
        and sequences of the process so far.
        """
        return astring.strip_console_codes(self.get_output())

    def is_alive(self):
        """
        Return True if the process is running.
        """
        return is_file_locked(self.lock_server_running_filename)

    def is_defunct(self):
        """
        Return True if the process is defunct (zombie).
        """
        return utils_process.process_in_ptree_is_defunct(self.get_pid())

    def kill(self, sig=signal.SIGKILL):
        """
        Kill the child process if alive
        """
        # Kill it if it's alive
        if self.is_alive():
            utils_process.kill_process_tree(self.get_pid(), sig)

    def close(self, sig=signal.SIGKILL):
        """
        Kill the child process if it's alive and remove temporary files.

        :param sig: The signal to send the process when attempting to kill it.
        """
        if not self.closed:
            self.kill(sig=sig)
            # Wait for the server to exit
            wait_for_lock(self.lock_server_running_filename)
            # Call all cleanup routines
            for hook in self.close_hooks:
                hook(self)
            # Close reader file descriptors
            self._close_reader_fds()
            self.reader_fds = {}
            # Remove all used files
            if 'AEXPECT_DEBUG' not in os.environ:
                shutil.rmtree(os.path.join(BASE_DIR, 'aexpect_%s' % self.a_id))
            self.closed = True

    def set_linesep(self, linesep):
        """
        Sets the line separator string (usually "\\n").

        :param linesep: Line separator string.
        """
        self.linesep = linesep

    def send(self, cont=""):
        """
        Send a string to the child process.

        :param cont: String to send to the child process.
        """
        try:
            proc_input_pipe = os.open(self.inpipe_filename, os.O_RDWR)
            os.write(proc_input_pipe, cont.encode(self.encoding))
            os.close(proc_input_pipe)
        except OSError:
            pass

    def sendline(self, cont=""):
        """
        Send a string followed by a line separator to the child process.

        :param cont: String to send to the child process.
        """
        self.send(cont + self.linesep)

    def sendcontrol(self, char):
        """
        This sends a control character to the child such as Ctrl-C or
        Ctrl-D. For example, to send a Ctrl-G (ASCII 7)::
        session.sendcontrol('g')
        :param char: single character you want to send (ctrl+$char)
        :raise KeyError: When unable to map char to ctrl+comand
        """
        char = char.lower()
        val = ord(char)
        if 97 <= val <= 122:
            val = val - 97 + 1  # ctrl+a = '\0x01'
            return self.send(chr(val))
        mapping = {'@': 0, '`': 0,
                   '[': 27, '{': 27,
                   '\\': 28, '|': 28,
                   ']': 29, '}': 29,
                   '^': 30, '~': 30,
                   '_': 31,
                   '?': 127}
        return self.send(chr(mapping[char]))

    def send_ctrl(self, control_str=""):
        """
        Send a control string to the aexpect process.

        :param control_str: Control string to send to the child process
                            container.
        """
        try:
            helper_control_pipe = os.open(self.ctrlpipe_filename, os.O_RDWR)
            data = "%10d%s" % (len(control_str), control_str)
            os.write(helper_control_pipe, data.encode(self.encoding))
            os.close(helper_control_pipe)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, etype, evalue, traceback):
        self.close()


class Tail(Spawn):

    """
    This class runs a child process in the background and sends its output in
    real time, line-by-line, to a callback function.

    See Spawn's docstring.

    This class uses a single pipe reader to read data in real time from the
    child process and report it to a given callback function.
    When the child process exits, its exit status is reported to an additional
    callback function.

    When this class is unpickled, it automatically resumes reporting output.
    """

    def __init__(self, command=None, a_id=None, auto_close=False, echo=False,
                 linesep="\n", termination_func=None, termination_params=(),
                 output_func=None, output_params=(), output_prefix="",
                 thread_name=None, pass_fds=(), encoding=None):
        """
        Initialize the class and run command as a child process.

        :param command: Command to run, or None if accessing an already running
                server.
        :param a_id: ID of an already running server, if accessing a running
                server, or None if starting a new one.
        :param auto_close: If True, close() the instance automatically when its
                reference count drops to zero (default False).
        :param echo: Boolean indicating whether echo should be initially
                enabled for the pseudo terminal running the subprocess.  This
                parameter has an effect only when starting a new server.
        :param linesep: Line separator to be appended to strings sent to the
                child process by sendline().
        :param termination_func: Function to call when the process exits.  The
                function must accept a single exit status parameter.
        :param termination_params: Parameters to send to termination_func
                before the exit status.
        :param output_func: Function to call whenever a line of output is
                available from the STDOUT or STDERR streams of the process.
                The function must accept a single string parameter.  The string
                does not include the final newline.
        :param output_params: Parameters to send to output_func before the
                output line.
        :param output_prefix: String to prepend to lines sent to output_func.
        :param thread_name: Name of thread to better identify hanging threads.
        :param pass_fds: Optional sequence of file descriptors to keep open
                between the parent and child.
        :param encoding: Override text encoding (by default: autodetect by
                locale.getpreferredencoding())
        """
        # Add a reader and a close hook
        self._add_reader("tail")
        self._add_close_hook(Tail._join_thread)
        self._add_close_hook(Tail._close_log_file)

        # Init the superclass
        super().__init__(command, a_id, auto_close, echo, linesep,
                         pass_fds, encoding)
        if thread_name is None:
            self.thread_name = "tail_thread_%s_%s" % (self.a_id,
                                                      str(command)[:10])
        else:
            self.thread_name = thread_name

        # Remember some attributes
        self.termination_func = termination_func
        self.termination_params = termination_params
        self.output_func = output_func
        self.output_params = output_params
        self.output_prefix = output_prefix

        # Start the thread in the background
        self.tail_thread = None
        if self.is_alive():
            if termination_func or output_func:
                self._start_thread()

    def __reduce__(self):
        return self.__class__, (self.__getinitargs__())

    def __getinitargs__(self):
        return Spawn.__getinitargs__(self) + (self.termination_func,
                                              self.termination_params,
                                              self.output_func,
                                              self.output_params,
                                              self.output_prefix,
                                              self.thread_name)

    def set_termination_func(self, termination_func):
        """
        Set the termination_func attribute. See __init__() for details.

        :param termination_func: Function to call when the process terminates.
                Must take a single parameter -- the exit status.
        """
        self.termination_func = termination_func
        if termination_func and not self.tail_thread:
            self._start_thread()

    def set_termination_params(self, termination_params):
        """
        Set the termination_params attribute. See __init__() for details.

        :param termination_params: Parameters to send to termination_func
                before the exit status.
        """
        self.termination_params = termination_params

    def set_output_func(self, output_func):
        """
        Set the output_func attribute. See __init__() for details.

        :param output_func: Function to call for each line of STDOUT/STDERR
                output from the process.  Must take a single string parameter.
        """
        self.output_func = output_func
        if output_func and not self.tail_thread:
            self._start_thread()

    def set_output_params(self, output_params):
        """
        Set the output_params attribute. See __init__() for details.

        :param output_params: Parameters to send to output_func before the
                output line.
        """
        self.output_params = output_params

    def set_output_prefix(self, output_prefix):
        """
        Set the output_prefix attribute. See __init__() for details.

        :param output_prefix: String to pre-pend to each line sent to
                output_func (see set_output_callback()).
        """
        self.output_prefix = output_prefix

    def set_log_file(self, filename):
        """
        Set a log file name for this tail instance.

        :param filename: Base name of the log.
        """
        self.log_file = filename

    def _close_log_file(self):
        if self.log_file is not None:
            genio.close_log_file(self.log_file)

    def _tail(self):  # speed optimization pylint: disable=too-many-branches
        def _print_line(text):
            # Pre-pend prefix and remove trailing whitespace
            text = self.output_prefix + text.rstrip()
            # Pass text to output_func
            try:
                out_params = self.output_params + (text,)
                self.output_func(*out_params)
            except TypeError:
                pass

        try:
            tail_pipe = self._get_fd("tail")
            poller = select.poll()
            poller.register(tail_pipe, select.POLLIN)
            bfr = ""
            while True:
                if _THREAD_KILL_REQUESTED.is_set():
                    try:
                        os.close(tail_pipe)
                    except OSError:
                        pass
                    return
                try:
                    # See if there's any data to read from the pipe
                    poll_status = poller.poll(50)
                except select.error:
                    break
                if poll_status:
                    # Some data is available; read it
                    new_data = os.read(tail_pipe, 1024)
                    if not new_data:
                        break
                    new_data = new_data.decode(self.encoding, "ignore")
                    if not new_data:    # all chars were ignored, skip round
                        continue
                    bfr += new_data
                    # Send the output to output_func line by line
                    # (except for the last line)
                    if self.output_func:
                        lines = bfr.split("\n")
                        for line in lines[:-1]:
                            _print_line(line)
                    # Leave only the last line
                    last_newline_index = bfr.rfind("\n")
                    bfr = bfr[last_newline_index + 1:]
                else:
                    # No output is available right now; flush the bfr
                    if bfr:
                        _print_line(bfr)
                        bfr = ""
            # The process terminated; print any remaining output
            if bfr:
                _print_line(bfr)
            # Get the exit status, print it and send it to termination_func
            status = self.get_status()
            if status is None:
                return
            _print_line("(Process terminated with status %s)" % status)
            try:
                params = self.termination_params + (status,)
                self.termination_func(*params)
            except TypeError:
                pass
        finally:
            self.tail_thread = None

    def _start_thread(self):
        self.tail_thread = threading.Thread(target=self._tail,
                                            name=self.thread_name)
        self.tail_thread.start()

    def _join_thread(self):
        # Wait for the tail thread to exit
        # (it's done this way because self.tail_thread may become None at any
        # time)
        thread = self.tail_thread
        if thread:
            thread.join()


class Expect(Tail):

    """
    This class runs a child process in the background and provides expect-like
    services.

    It also provides all of Tail's functionality.
    """

    def __init__(self, command=None, a_id=None, auto_close=True, echo=False,
                 linesep="\n", termination_func=None, termination_params=(),
                 output_func=None, output_params=(), output_prefix="",
                 thread_name=None, pass_fds=(), encoding=None):
        """
        Initialize the class and run command as a child process.

        :param command: Command to run, or None if accessing an already running
                server.
        :param a_id: ID of an already running server, if accessing a running
                server, or None if starting a new one.
        :param auto_close: If True, close() the instance automatically when its
                reference count drops to zero (default False).
        :param echo: Boolean indicating whether echo should be initially
                enabled for the pseudo terminal running the subprocess.  This
                parameter has an effect only when starting a new server.
        :param linesep: Line separator to be appended to strings sent to the
                child process by sendline().
        :param termination_func: Function to call when the process exits.  The
                function must accept a single exit status parameter.
        :param termination_params: Parameters to send to termination_func
                before the exit status.
        :param output_func: Function to call whenever a line of output is
                available from the STDOUT or STDERR streams of the process.
                The function must accept a single string parameter.  The string
                does not include the final newline.
        :param output_params: Parameters to send to output_func before the
                output line.
        :param output_prefix: String to prepend to lines sent to output_func.
        :param pass_fds: Optional sequence of file descriptors to keep open
                between the parent and child.
        :param encoding: Override text encoding (by default: autodetect by
                locale.getpreferredencoding())
        """
        # Add a reader
        self._add_reader("expect")

        # Init the superclass
        super().__init__(command, a_id, auto_close, echo, linesep,
                         termination_func, termination_params,
                         output_func, output_params, output_prefix, thread_name,
                         pass_fds, encoding)

    def __reduce__(self):
        return self.__class__, (self.__getinitargs__())

    def __getinitargs__(self):
        return Tail.__getinitargs__(self)

    def read_nonblocking(self, internal_timeout=None, timeout=None):
        """
        Read from child until there is nothing to read for timeout seconds.

        :param internal_timeout: Time (seconds) to wait before we give up
                                 reading from the child process, or None to
                                 use the default value.
        :param timeout: Timeout for reading child process output.
        """
        if internal_timeout is None:
            internal_timeout = 100
        else:
            internal_timeout *= 1000
        end_time = None
        if timeout:
            end_time = time.time() + timeout
        expect_pipe = self._get_fd("expect")
        poller = select.poll()
        poller.register(expect_pipe, select.POLLIN)
        data = ""
        while True:
            try:
                poll_status = poller.poll(internal_timeout)
            except select.error:
                return data
            if poll_status:
                new_data = os.read(expect_pipe, 1024).decode(self.encoding,
                                                             "ignore")
                if not new_data:
                    return data
                data += new_data
            else:
                return data
            if end_time and time.time() > end_time:
                return data

    @staticmethod
    def match_patterns(cont, patterns):
        """
        Match cont against a list of patterns.

        Return the index of the first pattern that matches a substring of cont.
        None and empty strings in patterns are ignored.
        If no match is found, return None.

        :param cont: input string
        :param patterns: List of strings (regular expression patterns).
        """
        for i, pattern in enumerate(patterns):
            if not pattern:
                continue
            if re.search(pattern, cont):
                return i
        return None

    @staticmethod
    def match_patterns_multiline(cont, patterns):
        """
        Match list of lines against a list of patterns.

        Return the index of the first pattern that matches a substring of cont.
        None and empty strings in patterns are ignored.
        If no match is found, return None.

        :param cont: List of strings (input strings)
        :param patterns: List of strings (regular expression patterns). The
                         pattern priority is from the last to first.
        """
        for i in range(-len(patterns), 0):
            if not patterns[i]:
                continue
            for line in cont:
                if re.search(patterns[i], line):
                    return i
        return None

    def read_until_output_matches(self, patterns, filter_func=lambda x: x,
                                  timeout=60.0, internal_timeout=None,
                                  print_func=None, match_func=None):
        """
        Read from child using read_nonblocking until a pattern matches.

        Read using read_nonblocking until a match is found using
        match_patterns, or until timeout expires. Before attempting to search
        for a match, the data is filtered using the filter_func function
        provided.

        :param patterns: List of strings (regular expression patterns)
        :param filter_func: Function to apply to the data read from the child
                before attempting to match it against the patterns (should take
                and return a string)
        :param timeout: The duration (in seconds) to wait until a match is
                found
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being read
                (should take a string parameter)
        :param match_func: Function to compare the output and patterns.
        :return: Tuple containing the match index and the data read so far
        :raise ExpectTimeoutError: Raised if timeout expires
        :raise ExpectProcessTerminatedError: Raised if the child process
                terminates while waiting for output
        :raise ExpectError: Raised if an unknown error occurs
        """
        if not match_func:
            match_func = self.match_patterns
        expect_pipe = self._get_fd("expect")
        poller = select.poll()
        poller.register(expect_pipe, select.POLLIN)
        output = ""
        end_time = time.time() + timeout
        while True:
            try:
                poll_timeout_ms = max(0, (end_time - time.time()) * 1000)
                poll_status = poller.poll(poll_timeout_ms)
            except select.error:
                break
            if not poll_status:
                raise ExpectTimeoutError(patterns, output)
            # Read data from child
            data = self.read_nonblocking(internal_timeout,
                                         end_time - time.time())
            if not data:
                break
            # Print it if necessary
            if print_func:
                for line in data.splitlines():
                    print_func(line)
            # Look for patterns
            output += data
            match = match_func(filter_func(output), patterns)
            if match is not None:
                return match, output

        # Check if the child has terminated
        if utils_wait.wait_for(lambda: not self.is_alive(), 5, 0, 0.1):
            raise ExpectProcessTerminatedError(patterns, self.get_status(),
                                               output)
        # This shouldn't happen
        raise ExpectError(patterns, output)

    def read_until_last_word_matches(self, patterns, timeout=60.0,
                                     internal_timeout=None, print_func=None):
        """
        Read using read_nonblocking until the last word of the output matches
        one of the patterns (using match_patterns), or until timeout expires.

        :param patterns: A list of strings (regular expression patterns)
        :param timeout: The duration (in seconds) to wait until a match is
                found
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being read
                (should take a string parameter)
        :return: A tuple containing the match index and the data read so far
        :raise ExpectTimeoutError: Raised if timeout expires
        :raise ExpectProcessTerminatedError: Raised if the child process
                terminates while waiting for output
        :raise ExpectError: Raised if an unknown error occurs
        """
        def _get_last_word(cont):
            if cont:
                return cont.split()[-1]
            return ""

        return self.read_until_output_matches(patterns, _get_last_word,
                                              timeout, internal_timeout,
                                              print_func)

    def read_until_last_line_matches(self, patterns, timeout=60.0,
                                     internal_timeout=None, print_func=None):
        """
        Read until the last non-empty line matches a pattern.

        Read using read_nonblocking until the last non-empty line of the output
        matches one of the patterns (using match_patterns), or until timeout
        expires. Return a tuple containing the match index (or None if no match
        was found) and the data read so far.

        :param patterns: A list of strings (regular expression patterns)
        :param timeout: The duration (in seconds) to wait until a match is
                found
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being read
                (should take a string parameter)
        :return: A tuple containing the match index and the data read so far
        :raise ExpectTimeoutError: Raised if timeout expires
        :raise ExpectProcessTerminatedError: Raised if the child process
                terminates while waiting for output
        :raise ExpectError: Raised if an unknown error occurs
        """
        def _get_last_nonempty_line(cont):
            nonempty_lines = [l for l in cont.splitlines() if l.strip()]
            if nonempty_lines:
                return nonempty_lines[-1]
            return ""

        return self.read_until_output_matches(patterns,
                                              _get_last_nonempty_line,
                                              timeout, internal_timeout,
                                              print_func)

    def read_until_any_line_matches(self, patterns, timeout=60.0,
                                    internal_timeout=None, print_func=None):
        """
        Read using read_nonblocking until any line matches a pattern.

        Read using read_nonblocking until any line of the output matches
        one of the patterns (using match_patterns_multiline), or until timeout
        expires. Return a tuple containing the match index (or None if no match
        was found) and the data read so far.

        :param patterns: A list of strings (regular expression patterns)
                         Consider using '^' in the beginning.
        :param timeout: The duration (in seconds) to wait until a match is
                found
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being read
                (should take a string parameter)
        :return: A tuple containing the match index and the data read so far
        :raise ExpectTimeoutError: Raised if timeout expires
        :raise ExpectProcessTerminatedError: Raised if the child process
                terminates while waiting for output
        :raise ExpectError: Raised if an unknown error occurs
        """
        return self.read_until_output_matches(patterns,
                                              lambda x: x.splitlines(),
                                              timeout, internal_timeout,
                                              print_func,
                                              self.match_patterns_multiline)


class ShellSession(Expect):

    """
    This class runs a child process in the background.  It it suited for
    processes that provide an interactive shell, such as SSH and Telnet.

    It provides all services of Expect and Tail.  In addition, it
    provides command running services, and a utility function to test the
    process for responsiveness.
    """

    # Return code pattern of shell interpreter
    __RE_STATUS = re.compile("^-?[0-9]+$")

    def __init__(self, command=None, a_id=None, auto_close=True, echo=False,
                 linesep="\n", termination_func=None, termination_params=(),
                 output_func=None, output_params=(), output_prefix="",
                 thread_name=None, prompt=r"[\#\$]\s*$",
                 status_test_command="echo $?", pass_fds=(), encoding=None):
        """
        Initialize the class and run command as a child process.

        :param command: Command to run, or None if accessing an already running
                server.
        :param a_id: ID of an already running server, if accessing a running
                server, or None if starting a new one.
        :param auto_close: If True, close() the instance automatically when its
                reference count drops to zero (default True).
        :param echo: Boolean indicating whether echo should be initially
                enabled for the pseudo terminal running the subprocess.  This
                parameter has an effect only when starting a new server.
        :param linesep: Line separator to be appended to strings sent to the
                child process by sendline().
        :param termination_func: Function to call when the process exits.  The
                function must accept a single exit status parameter.
        :param termination_params: Parameters to send to termination_func
                before the exit status.
        :param output_func: Function to call whenever a line of output is
                available from the STDOUT or STDERR streams of the process.
                The function must accept a single string parameter.  The string
                does not include the final newline.
        :param output_params: Parameters to send to output_func before the
                output line.
        :param output_prefix: String to prepend to lines sent to output_func.
        :param prompt: Regular expression describing the shell's prompt line.
        :param status_test_command: Command to be used for getting the last
                exit status of commands run inside the shell (used by
                cmd_status_output() and friends).
        :param pass_fds: Optional sequence of file descriptors to keep open
                between the parent and child.
        :param encoding: Override text encoding (by default: autodetect by
                locale.getpreferredencoding())
        """
        # Init the superclass
        super().__init__(command, a_id, auto_close, echo, linesep,
                         termination_func, termination_params,
                         output_func, output_params, output_prefix, thread_name,
                         pass_fds, encoding)

        # Remember some attributes
        self.prompt = prompt
        self.status_test_command = status_test_command

    def __reduce__(self):
        return self.__class__, (self.__getinitargs__())

    def __getinitargs__(self):
        return Expect.__getinitargs__(self) + (self.prompt,
                                               self.status_test_command)

    @classmethod
    def remove_command_echo(cls, cont, cmd):
        """
        Remove the executed command which might have been echoed by terminal
        into output.
        """
        if cont and cont.splitlines()[0] == cmd:
            cont = "".join(cont.splitlines(True)[1:])
        return cont

    @classmethod
    def remove_last_nonempty_line(cls, cont):
        """Remove last non-empty line and all following empty lines"""
        return "".join(cont.rstrip().splitlines(True)[:-1])

    def set_prompt(self, prompt):
        """
        Set the prompt attribute for later use by read_up_to_prompt.

        :param prompt: String that describes the prompt contents.
        """
        self.prompt = prompt

    def set_status_test_command(self, status_test_command):
        """
        Set the command to be sent in order to get the last exit status.

        :param status_test_command: Command that will be sent to get the last
                exit status.
        """
        self.status_test_command = status_test_command

    def is_responsive(self, timeout=5.0):
        """
        Return True if the process responds to STDIN/terminal input.

        Send a newline to the child process (e.g. SSH or Telnet) and read some
        output using read_nonblocking().
        If all is OK, some output should be available (e.g. the shell prompt).
        In that case return True.  Otherwise return False.

        :param timeout: Time duration to wait before the process is considered
                unresponsive.
        """
        # Read all output that's waiting to be read, to make sure the output
        # we read next is in response to the newline sent
        self.read_nonblocking(internal_timeout=0, timeout=timeout)
        # Send a newline
        self.sendline()
        # Wait up to timeout seconds for some output from the child
        end_time = time.time() + timeout
        while time.time() < end_time:
            time.sleep(0.5)
            if self.read_nonblocking(0, end_time - time.time()).strip():
                return True
        # No output -- report unresponsive
        return False

    def read_up_to_prompt(self, timeout=60.0, internal_timeout=None,
                          print_func=None):
        """
        Read until the last non-empty line matches the prompt.

        Read using read_nonblocking until the last non-empty line of the output
        matches the prompt regular expression set by set_prompt, or until
        timeout expires.

        :param timeout: The duration (in seconds) to wait until a match is
                found
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being
                read (should take a string parameter)

        :return: The data read so far
        :raise ExpectTimeoutError: Raised if timeout expires
        :raise ExpectProcessTerminatedError: Raised if the shell process
                terminates while waiting for output
        :raise ExpectError: Raised if an unknown error occurs
        """
        return self.read_until_last_line_matches([self.prompt], timeout,
                                                 internal_timeout,
                                                 print_func)[1]

    def cmd_output(self, cmd, timeout=60, internal_timeout=None,
                   print_func=None, safe=False):
        """
        Send a command and return its output.

        :param cmd: Command to send (must not contain newline characters)
        :param timeout: The duration (in seconds) to wait for the prompt to
                return
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being read
                (should take a string parameter)
        :param safe: Whether using safe mode when execute cmd.
                In serial sessions, frequently the kernel might print debug or
                error messages that make read_up_to_prompt to timeout. Let's
                try to be a little more robust and send a carriage return, to
                see if we can get to the prompt when safe=True.

        :return: The output of cmd
        :raise ShellTimeoutError: Raised if timeout expires
        :raise ShellProcessTerminatedError: Raised if the shell process
                terminates while waiting for output
        :raise ShellError: Raised if an unknown error occurs
        """
        if safe:
            return self.cmd_output_safe(cmd, timeout)
        logging.debug("Sending command: %s", cmd)
        self.read_nonblocking(0, timeout)
        self.sendline(cmd)
        try:
            out = self.read_up_to_prompt(timeout, internal_timeout, print_func)
        except ExpectTimeoutError as error:
            output = self.remove_command_echo(error.output, cmd)
            raise ShellTimeoutError(cmd, output) from error
        except ExpectProcessTerminatedError as error:
            output = self.remove_command_echo(error.output, cmd)
            raise ShellProcessTerminatedError(cmd, error.status, output) from error
        except ExpectError as error:
            output = self.remove_command_echo(error.output, cmd)
            raise ShellError(cmd, output) from error

        # Remove the echoed command and the final shell prompt
        return self.remove_last_nonempty_line(self.remove_command_echo(out,
                                                                       cmd))

    def cmd_output_safe(self, cmd, timeout=60):
        """
        Send a command and return its output (serial sessions).

        In serial sessions, frequently the kernel might print debug or
        error messages that make read_up_to_prompt to timeout. Let's try
        to be a little more robust and send a carriage return, to see if
        we can get to the prompt.

        :param cmd: Command to send (must not contain newline characters)
        :param timeout: The duration (in seconds) to wait for the prompt to
                return

        :return: The output of cmd
        :raise ShellTimeoutError: Raised if timeout expires
        :raise ShellProcessTerminatedError: Raised if the shell process
                terminates while waiting for output
        :raise ShellError: Raised if an unknown error occurs
        """
        logging.debug("Sending command (safe): %s", cmd)
        self.read_nonblocking(0, timeout)
        self.sendline(cmd)
        out = ""
        success = False
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            try:
                out += self.read_up_to_prompt(0.5)
                success = True
                break
            except ExpectTimeoutError as error:
                self.sendline()
            except ExpectProcessTerminatedError as error:
                output = self.remove_command_echo(error.output, cmd)
                raise ShellProcessTerminatedError(cmd, error.status, output) from error
            except ExpectError as error:
                output = self.remove_command_echo(error.output, cmd)
                raise ShellError(cmd, output) from error

        if not success:
            raise ShellTimeoutError(cmd, out)

        # Remove the echoed command and the final shell prompt
        return self.remove_last_nonempty_line(self.remove_command_echo(out,
                                                                       cmd))

    def cmd_status_output(self, cmd, timeout=60, internal_timeout=None,
                          print_func=None, safe=False):
        """
        Send a command and return its exit status and output.

        :param cmd: Command to send (must not contain newline characters)
        :param timeout: The duration (in seconds) to wait for the prompt to
                return
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being read
                (should take a string parameter)
        :param safe: Whether using safe mode when execute cmd.
                In serial sessions, frequently the kernel might print debug or
                error messages that make read_up_to_prompt to timeout. Let'status
                try to be a little more robust and send a carriage return, to
                see if we can get to the prompt when safe=True.

        :return: A tuple (status, output) where status is the exit status and
                output is the output of cmd
        :raise ShellTimeoutError: Raised if timeout expires
        :raise ShellProcessTerminatedError: Raised if the shell process
                terminates while waiting for output
        :raise ShellStatusError: Raised if the exit status cannot be obtained
        :raise ShellError: Raised if an unknown error occurs
        """
        out = self.cmd_output(cmd, timeout, internal_timeout, print_func, safe)
        try:
            # Send the 'echo $?' (or equivalent) command to get the exit status
            status = self.cmd_output(self.status_test_command, 30,
                                     internal_timeout, print_func, safe)
        except ShellError as error:
            raise ShellStatusError(cmd, out) from error

        # Get the first line consisting of digits only
        digit_lines = [l for l in status.splitlines()
                       if self.__RE_STATUS.match(l.strip())]
        if digit_lines:
            return int(digit_lines[0].strip()), out
        raise ShellStatusError(cmd, out)

    def cmd_status(self, cmd, timeout=60, internal_timeout=None,
                   print_func=None, safe=False):
        """
        Send a command and return its exit status.

        :param cmd: Command to send (must not contain newline characters)
        :param timeout: The duration (in seconds) to wait for the prompt to
                return
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being read
                (should take a string parameter)
        :param safe: Whether using safe mode when execute cmd.
                In serial sessions, frequently the kernel might print debug or
                error messages that make read_up_to_prompt to timeout. Let's
                try to be a little more robust and send a carriage return, to
                see if we can get to the prompt when safe=True.

        :return: The exit status of cmd
        :raise ShellTimeoutError: Raised if timeout expires
        :raise ShellProcessTerminatedError: Raised if the shell process
                terminates while waiting for output
        :raise ShellStatusError: Raised if the exit status cannot be obtained
        :raise ShellError: Raised if an unknown error occurs
        """
        return self.cmd_status_output(cmd, timeout, internal_timeout,
                                      print_func, safe)[0]

    def cmd(self, cmd, timeout=60, internal_timeout=None, print_func=None,
            ok_status=None, ignore_all_errors=False):
        """
        Send a command and return its output. If the command'status exit status is
        nonzero, raise an exception.

        :param cmd: Command to send (must not contain newline characters)
        :param timeout: The duration (in seconds) to wait for the prompt to
                return
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being read
                (should take a string parameter)
        :param ok_status: do not raise ShellCmdError in case that exit status
                is one of ok_status. (default is [0,])
        :param ignore_all_errors: toggles whether or not an exception should be
                raised  on any error.

        :return: The output of cmd
        :raise ShellTimeoutError: Raised if timeout expires
        :raise ShellProcessTerminatedError: Raised if the shell process
                terminates while waiting for output
        :raise ShellError: Raised if the exit status cannot be obtained or if
                an unknown error occurs
        :raise ShellStatusError: Raised if the exit status cannot be obtained
        :raise ShellError: Raised if an unknown error occurs
        :raise ShellCmdError: Raised if the exit status is nonzero
        """
        if ok_status is None:
            ok_status = [0, ]
        try:
            status, output = self.cmd_status_output(cmd, timeout,
                                                    internal_timeout,
                                                    print_func)
            if status not in ok_status:
                raise ShellCmdError(cmd, status, output)
            return output
        except ShellError:
            if ignore_all_errors:
                pass
            else:
                raise

    def get_command_output(self, cmd, timeout=60, internal_timeout=None,
                           print_func=None):
        """
        Alias for cmd_output() for backward compatibility.
        """
        return self.cmd_output(cmd, timeout, internal_timeout, print_func)

    def get_command_status_output(self, cmd, timeout=60, internal_timeout=None,
                                  print_func=None):
        """
        Alias for cmd_status_output() for backward compatibility.
        """
        return self.cmd_status_output(cmd, timeout, internal_timeout,
                                      print_func)

    def get_command_status(self, cmd, timeout=60, internal_timeout=None,
                           print_func=None):
        """
        Alias for cmd_status() for backward compatibility.
        """
        return self.cmd_status(cmd, timeout, internal_timeout, print_func)


class RemoteSession(ShellSession):

    """
    This class includes helpers specifically with regards to remote sessions.

    It provides all services of the shell session and extends it with remote
    connection attributes like client, host, port, username, and password.
    """

    def __init__(self, command=None, a_id=None, auto_close=True, echo=False,
                 linesep="\n", termination_func=None, termination_params=(),
                 output_func=None, output_params=(), output_prefix="",
                 thread_name=None, prompt=r"[\#\$]\s*$",
                 status_test_command="echo $?",
                 client="ssh", host="localhost", port=22,
                 username="root", password="test1234",
                 pass_fds=(), encoding=None):
        """
        Initialize the class and run command as a child process.

        :param command: Command to run, or None if accessing an already running
                server.
        :param a_id: ID of an already running server, if accessing a running
                server, or None if starting a new one.
        :param auto_close: If True, close() the instance automatically when its
                reference count drops to zero (default True).
        :param echo: Boolean indicating whether echo should be initially
                enabled for the pseudo terminal running the subprocess.  This
                parameter has an effect only when starting a new server.
        :param linesep: Line separator to be appended to strings sent to the
                child process by sendline().
        :param termination_func: Function to call when the process exits.  The
                function must accept a single exit status parameter.
        :param termination_params: Parameters to send to termination_func
                before the exit status.
        :param output_func: Function to call whenever a line of output is
                available from the STDOUT or STDERR streams of the process.
                The function must accept a single string parameter.  The string
                does not include the final newline.
        :param output_params: Parameters to send to output_func before the
                output line.
        :param output_prefix: String to prepend to lines sent to output_func.
        :param prompt: Regular expression describing the shell's prompt line.
        :param status_test_command: Command to be used for getting the last
                exit status of commands run inside the shell (used by
                cmd_status_output() and friends).
        :param client: String client to use for the remote connection.
        :param host: String host to use for the remote connection.
        :param port: Integer port to use for the remote connection.
        :param username: String to use as username for remote authentication.
        :param password: String to use as password for remote authentication.
        :param pass_fds: Optional sequence of file descriptors to keep open
                between the parent and child.
        :param encoding: Override text encoding (by default: autodetect by
                locale.getpreferredencoding())
        """
        # Init the superclass
        super().__init__(command, a_id, auto_close, echo, linesep,
                         termination_func, termination_params,
                         output_func, output_params, output_prefix, thread_name,
                         prompt, status_test_command,
                         pass_fds, encoding)

        # Remember some attributes
        self.client = client
        self.host = host
        self.port = port
        self.username = username
        self.password = password


def run_tail(command, termination_func=None, output_func=None,
             output_prefix="", timeout=1.0, auto_close=True, pass_fds=(),
             encoding=None):
    """
    Run a subprocess in the background and collect its output and exit status.

    Run command as a subprocess.  Call output_func with each line of output
    from the subprocess (prefixed by output_prefix).  Call termination_func
    when the subprocess terminates.  Return when timeout expires or when the
    subprocess exits -- whichever occurs first.

    :param command: The shell command to execute
    :param termination_func: A function to call when the process terminates
            (should take an integer exit status parameter)
    :param output_func: A function to call with each line of output from
            the subprocess (should take a string parameter)
    :param output_prefix: A string to pre-pend to each line of the output,
            before passing it to stdout_func
    :param timeout: Time duration (in seconds) to wait for the subprocess to
            terminate before returning
    :param auto_close: If True, close() the instance automatically when its
            reference count drops to zero (default False).
    :param pass_fds: Optional sequence of file descriptors to keep open
            between the parent and child.
    :param encoding: Override text encoding (by default: autodetect by
            locale.getpreferredencoding())

    :return: A Expect object.
    """
    bg_process = Tail(command=command,
                      termination_func=termination_func,
                      output_func=output_func,
                      output_prefix=output_prefix,
                      auto_close=auto_close,
                      pass_fds=pass_fds,
                      encoding=encoding)

    end_time = time.time() + timeout
    while time.time() < end_time and bg_process.is_alive():
        time.sleep(0.1)

    return bg_process


def run_bg(command, termination_func=None, output_func=None, output_prefix="",
           timeout=1.0, auto_close=True, pass_fds=(), encoding=None):
    """
    Run a subprocess in the background and collect its output and exit status.

    Run command as a subprocess.  Call output_func with each line of output
    from the subprocess (prefixed by output_prefix).  Call termination_func
    when the subprocess terminates.  Return when timeout expires or when the
    subprocess exits -- whichever occurs first.

    :param command: The shell command to execute
    :param termination_func: A function to call when the process terminates
            (should take an integer exit status parameter)
    :param output_func: A function to call with each line of output from
            the subprocess (should take a string parameter)
    :param output_prefix: A string to pre-pend to each line of the output,
            before passing it to stdout_func
    :param timeout: Time duration (in seconds) to wait for the subprocess to
            terminate before returning
    :param auto_close: If True, close() the instance automatically when its
            reference count drops to zero (default False).
    :param pass_fds: Optional sequence of file descriptors to keep open
            between the parent and child.
    :param encoding: Override text encoding (by default: autodetect by
            locale.getpreferredencoding())

    :return: A Expect object.
    """
    bg_process = Expect(command=command,
                        termination_func=termination_func,
                        output_func=output_func,
                        output_prefix=output_prefix,
                        auto_close=auto_close,
                        pass_fds=pass_fds,
                        encoding=encoding)

    end_time = time.time() + timeout
    while time.time() < end_time and bg_process.is_alive():
        time.sleep(0.1)

    return bg_process


def run_fg(command, output_func=None, output_prefix="", timeout=1.0,
           pass_fds=(), encoding=None):
    """
    Run a subprocess in the foreground and collect its output and exit status.

    Run command as a subprocess.  Call output_func with each line of output
    from the subprocess (prefixed by prefix).  Return when timeout expires or
    when the subprocess exits -- whichever occurs first.  If timeout expires
    and the subprocess is still running, kill it before returning.

    :param command: The shell command to execute
    :param output_func: A function to call with each line of output from
            the subprocess (should take a string parameter)
    :param output_prefix: A string to pre-pend to each line of the output,
            before passing it to stdout_func
    :param timeout: Time duration (in seconds) to wait for the subprocess to
            terminate before killing it and returning
    :param pass_fds: Optional sequence of file descriptors to keep open
            between the parent and child.
    :param encoding: Override text encoding (by default: autodetect by
            locale.getpreferredencoding())

    :return: A 2-tuple containing the exit status of the process and its
            STDOUT/STDERR output.  If timeout expires before the process
            terminates, the returned status is None.
    """
    bg_process = run_bg(command, None, output_func, output_prefix, timeout,
                        pass_fds=pass_fds, encoding=encoding)
    output = bg_process.get_output()
    if bg_process.is_alive():
        status = None
    else:
        status = bg_process.get_status()
    bg_process.close()
    return status, output
