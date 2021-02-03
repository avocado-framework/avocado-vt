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

# from aexpect.exceptions import ExpectError
# from aexpect.exceptions import ExpectProcessTerminatedError
# from aexpect.exceptions import ExpectTimeoutError
# from aexpect.exceptions import ShellCmdError
# from aexpect.exceptions import ShellError
# from aexpect.exceptions import ShellProcessTerminatedError
# from aexpect.exceptions import ShellStatusError
# from aexpect.exceptions import ShellTimeoutError

# from aexpect.shared import BASE_DIR
# from aexpect.shared import get_filenames
# from aexpect.shared import get_reader_filename
# from aexpect.shared import get_lock_fd
# from aexpect.shared import is_file_locked
# from aexpect.shared import unlock_fd
from remote_aexpect.shared import wait_for_lock

# from aexpect.utils import astring
# from aexpect.utils import data_factory
# from aexpect.utils import genio
# from aexpect.utils import process as utils_process
# from aexpect.utils import path as utils_path
# from aexpect.utils import wait as utils_wait


def get_pid(shell_pid_filename):
    """
    Return the PID of the process.

    Note: this may be the PID of the shell process running the user given
    command.
    """
    try:
        with open(shell_pid_filename, 'r') as pid_file:
            try:
                return int(pid_file.read())
            except ValueError:
                return None
    except IOError:
        return None


def get_status(lock_server_running_filename, status_filename):
    """
    Wait for the process to exit and return its exit status, or None
    if the exit status is not available.
    """
    wait_for_lock(lock_server_running_filename)
    try:
        with open(status_filename, 'r') as status_file:
            try:
                return int(status_file.read())
            except ValueError:
                return None
    except IOError:
        return None


def get_output(output_filename, encoding):
    """
    Return the STDOUT and STDERR output of the process so far.
    """
    try:
        with open(output_filename, 'rb') as output_file:
            return output_file.read().decode(encoding, 'backslashreplace')
    except IOError:
        return None


def send(inpipe_filename, cont, encoding):
    """
    Send a string to the child process.

    :param cont: String to send to the child process.
    """
    try:
        proc_input_pipe = os.open(inpipe_filename, os.O_RDWR)
        os.write(proc_input_pipe, cont.encode(encoding))
        os.close(proc_input_pipe)
    except OSError:
        pass


def send_ctrl(ctrlpipe_filename, control_str, encoding):
    """
    Send a control string to the aexpect process.

    :param control_str: Control string to send to the child process
                        container.
    """
    try:
        helper_control_pipe = os.open(ctrlpipe_filename, os.O_RDWR)
        data = "%10d%s" % (len(control_str), control_str)
        os.write(helper_control_pipe, data.encode(encoding))
        os.close(helper_control_pipe)
    except OSError:
        pass
