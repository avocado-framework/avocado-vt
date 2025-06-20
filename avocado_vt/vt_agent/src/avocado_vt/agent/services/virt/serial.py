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
Serial console service module for Avocado-VT agent.

This module provides a high-level interface for managing serial console
connections to virtual machines. It wraps the console manager functionality
and provides convenient functions for common serial console operations
such as login, command execution, and data reading.

Functions:
    create_serial: Create a new serial console connection
    login_serial: Login to a serial console with credentials
    close_serial: Close a serial console connection
    is_alive_serial: Check if a serial console is alive
    cmd: Execute commands with status checking
    cmd_output: Execute commands and return output
    cmd_status: Execute commands and return status
    send/sendline: Send data to serial console
    read_*: Various reading operations from serial console

The module integrates with aexpect for remote operations and provides
error handling for common serial console exceptions.
"""

import logging
import re

from avocado_vt.agent.managers import console_mgr, vmm
from virttest import utils_misc

from aexpect import remote
from aexpect.exceptions import (
    ExpectError,
    ExpectProcessTerminatedError,
    ExpectTimeoutError,
)

VMM = vmm.VirtualMachinesManager()
LOG = logging.getLogger("avocado.service." + __name__)


def create_serial(
    instance_id, name, linesep="\n", prompt=r"[\#\$]\s*$", status_test_command="echo $?"
):
    """
    Create a new serial console connection for a virtual machine instance.
    
    :param instance_id: Unique identifier for the VM instance
    :type instance_id: str
    :param name: Name identifier for the serial console
    :type name: str
    :param linesep: Line separator character for the console
    :type linesep: str
    :param prompt: Regular expression pattern for the shell prompt
    :type prompt: str
    :param status_test_command: Command to test the exit status
    :type status_test_command: str
    :return: Unique identifier for the created serial console
    :rtype: str
    """
    params = {
        "linesep": linesep,
        "prompt": prompt,
        "status_test_command": status_test_command,
    }
    instance_driver = VMM.get_driver(instance_id)
    filename = instance_driver.get_serial_info(name, "filename")
    console = console_mgr.create_console(name, instance_id, "serial", filename, params)
    serial_id = utils_misc.generate_random_string(16)
    console_mgr.register_console(serial_id, console)
    return serial_id


def login_serial(serial_id, username, password, prompt, timeout=10):
    """
    Login to a serial console using username and password credentials.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param username: Username for login
    :type username: str
    :param password: Password for login
    :type password: str
    :param prompt: Regular expression pattern for the shell prompt after login
    :type prompt: str
    :param timeout: Timeout in seconds for login operation
    :type timeout: int
    :return: Output from the login process
    :rtype: bytes
    :raises LoginTimeoutError: If login times out
    :raises LoginProcessTerminatedError: If login process terminates unexpectedly
    :raises LoginAuthenticationError: If authentication fails
    :raises LoginError: For other login-related errors
    """
    serial = console_mgr.get_console(serial_id)
    prompt = re.compile(prompt)
    try:
        output = remote.handle_prompts(serial, username, password, prompt, timeout)
        if isinstance(output, str):
            output = output.encode("utf-8", "ignore")
        return output
    except Exception as e:
        if isinstance(e, remote.LoginTimeoutError):
            output = e.output
            if isinstance(e.output, str):
                output = e.output.encode("utf-8", "ignore")
            raise remote.LoginTimeoutError(output)
        elif isinstance(e, remote.LoginProcessTerminatedError):
            output = e.output
            if isinstance(e.output, str):
                output = e.output.encode("utf-8", "ignore")
            raise remote.LoginProcessTerminatedError(e.status, output)
        elif isinstance(e, remote.LoginAuthenticationError):
            output = e.output
            if isinstance(e.output, str):
                output = e.output.encode("utf-8", "ignore")
            raise remote.LoginProcessTerminatedError(output)
        elif isinstance(e, remote.LoginError):
            output = e.output
            if isinstance(e.output, str):
                output = e.output.encode("utf-8", "ignore")
            raise remote.LoginError(e.msg, output)
        raise e


def close_serial(serial_id):
    """
    Close a serial console connection.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    """
    serial = console_mgr.get_console(serial_id)
    serial.close()


def is_alive_serial(serial_id):
    """
    Check if a serial console connection is alive and responsive.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :return: True if the serial console is alive, False otherwise
    :rtype: bool
    """
    serial = console_mgr.get_console(serial_id)
    return serial.is_alive()


def cmd(serial_id, cmd, timeout=60, ok_status=None, ignore_all_errors=False):
    """
    Execute a command on the serial console and check its exit status.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param cmd: Command to execute
    :type cmd: str
    :param timeout: Timeout in seconds for command execution
    :type timeout: int
    :param ok_status: List of acceptable exit status codes
    :type ok_status: list or None
    :param ignore_all_errors: Whether to ignore all command errors
    :type ignore_all_errors: bool
    :return: Command output
    :rtype: str
    """
    serial = console_mgr.get_console(serial_id)
    return serial.cmd(
        cmd=cmd,
        timeout=timeout,
        ok_status=ok_status,
        ignore_all_errors=ignore_all_errors,
    )


def cmd_output(serial_id, cmd, timeout=60, safe=False):
    """
    Execute a command and return its output without status checking.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param cmd: Command to execute
    :type cmd: str
    :param timeout: Timeout in seconds for command execution
    :type timeout: int
    :param safe: Whether to use safe mode (ignore non-zero exit status)
    :type safe: bool
    :return: Command output
    :rtype: str
    """
    serial = console_mgr.get_console(serial_id)
    return serial.cmd_output(cmd=cmd, timeout=timeout, safe=safe)


def cmd_output_safe(serial_id, cmd, timeout=60):
    """
    Execute a command safely and return its output, ignoring exit status.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param cmd: Command to execute
    :type cmd: str
    :param timeout: Timeout in seconds for command execution
    :type timeout: int
    :return: Command output
    :rtype: str
    """
    serial = console_mgr.get_console(serial_id)
    return serial.cmd_output_safe(cmd=cmd, timeout=timeout)


def cmd_status(serial_id, cmd, timeout=60, safe=False):
    """
    Execute a command and return its exit status.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param cmd: Command to execute
    :type cmd: str
    :param timeout: Timeout in seconds for command execution
    :type timeout: int
    :param safe: Whether to use safe mode
    :type safe: bool
    :return: Command exit status
    :rtype: int
    """
    serial = console_mgr.get_console(serial_id)
    return serial.cmd_status(cmd=cmd, timeout=timeout, safe=safe)


def cmd_status_output(serial_id, cmd, timeout=60, safe=False):
    """
    Execute a command and return both its exit status and output.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param cmd: Command to execute
    :type cmd: str
    :param timeout: Timeout in seconds for command execution
    :type timeout: int
    :param safe: Whether to use safe mode
    :type safe: bool
    :return: Tuple of (exit_status, output)
    :rtype: tuple
    """
    serial = console_mgr.get_console(serial_id)
    return serial.cmd_status_output(cmd=cmd, timeout=timeout, safe=safe)


def is_responsive(serial_id):
    """
    Check if the serial console is responsive to commands.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :return: True if the console is responsive, False otherwise
    :rtype: bool
    """
    serial = console_mgr.get_console(serial_id)
    return serial.is_responsive()


def send(serial_id, cont=""):
    """
    Send content to the serial console without adding a line separator.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param cont: Content to send
    :type cont: str
    """
    serial = console_mgr.get_console(serial_id)
    serial.send(cont)


def sendline(serial_id, cont=""):
    """
    Send content to the serial console followed by a line separator.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param cont: Content to send
    :type cont: str
    """
    serial = console_mgr.get_console(serial_id)
    serial.sendline(cont)


def sendcontrol(serial_id, char):
    """
    Send a control character to the serial console.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param char: Control character to send
    :type char: str
    :return: Result of the send operation
    :rtype: Any
    """
    serial = console_mgr.get_console(serial_id)
    serial.sendcontrol(char)


def send_ctrl(serial_id, control_str=""):
    """
    Send a control string to the serial console.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param control_str: Control string to send
    :type control_str: str
    """
    serial = console_mgr.get_console(serial_id)
    serial.send_ctrl(control_str)


def set_linesep(serial_id, linesep):
    """
    Set the line separator for the serial console.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param linesep: Line separator character or string
    :type linesep: str
    """
    serial = console_mgr.get_console(serial_id)
    serial.set_linesep(linesep)


def set_status_test_command(serial_id, command):
    """
    Set the command used to test command exit status.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param command: Command to use for status testing
    :type command: str
    """
    serial = console_mgr.get_console(serial_id)
    serial.set_status_test_command(command)


def read_nonblocking(serial_id, timeout=60, internal_timeout=None):
    """
    Read data from the serial console in non-blocking mode.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param timeout: Timeout in seconds for the read operation
    :type timeout: int
    :param internal_timeout: Internal timeout for the operation
    :type internal_timeout: float or None
    :return: Data read from the console
    :rtype: bytes
    """
    serial = console_mgr.get_console(serial_id)
    data = serial.read_nonblocking(timeout=timeout, internal_timeout=internal_timeout)
    if isinstance(data, str):
        data = data.encode("utf-8", "ignore")
    return data


def read_until_output_matches(serial_id, patterns, timeout=60, internal_timeout=None):
    """
    Read from the console until the output matches one of the given patterns.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param patterns: List of regular expression patterns to match
    :type patterns: list
    :param timeout: Timeout in seconds for the read operation
    :type timeout: int
    :param internal_timeout: Internal timeout for the operation
    :type internal_timeout: float or None
    :return: Match result and output
    :rtype: tuple
    """
    serial = console_mgr.get_console(serial_id)
    _patterns = []
    for pattern in patterns:
        _patterns.append(re.compile(pattern))
    return serial.read_until_output_matches(
        _patterns, timeout=timeout, internal_timeout=internal_timeout
    )


def read_until_last_line_matches(
    serial_id, patterns, timeout=60, internal_timeout=None
):
    """
    Read from the console until the last line matches one of the given patterns.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param patterns: List of regular expression patterns to match
    :type patterns: list
    :param timeout: Timeout in seconds for the read operation
    :type timeout: int
    :param internal_timeout: Internal timeout for the operation
    :type internal_timeout: float or None
    :return: Tuple of (match_index, output). Returns (-1, output) on timeout,
             (-2, output) on process termination, (-3, output) on other errors
    :rtype: tuple
    """
    serial = console_mgr.get_console(serial_id)
    _patterns = []
    for pattern in patterns:
        _patterns.append(re.compile(pattern))

    try:
        match, output = serial.read_until_last_line_matches(
            _patterns, timeout=timeout, internal_timeout=internal_timeout
        )
        if isinstance(output, str):
            output = output.encode("utf-8", "ignore")
        return match, output

    except ExpectTimeoutError as e:
        output = e.output
        if isinstance(output, str):
            output = output.encode("utf-8", "ignore")
        return -1, output

    except ExpectProcessTerminatedError as e:
        output = e.output
        if isinstance(output, str):
            output = output.encode("utf-8", "ignore")
        return -2, output

    except ExpectError as e:
        output = e.output
        if isinstance(output, str):
            output = output.encode("utf-8", "ignore")
        return -3, output


def read_until_any_line_matches(serial_id, patterns, timeout=60, internal_timeout=None):
    """
    Read from the console until any line matches one of the given patterns.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param patterns: List of regular expression patterns to match
    :type patterns: list
    :param timeout: Timeout in seconds for the read operation
    :type timeout: int
    :param internal_timeout: Internal timeout for the operation
    :type internal_timeout: float or None
    :return: Match result and output
    :rtype: tuple
    """
    serial = console_mgr.get_console(serial_id)
    _patterns = []
    for pattern in patterns:
        _patterns.append(re.compile(pattern))
    return serial.read_until_any_line_matches(
        patterns, timeout=timeout, internal_timeout=internal_timeout
    )


def read_up_to_prompt(serial_id, timeout=60, internal_timeout=None):
    """
    Read from the console up to the shell prompt.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :param timeout: Timeout in seconds for the read operation
    :type timeout: int
    :param internal_timeout: Internal timeout for the operation
    :type internal_timeout: float or None
    :return: Output read up to the prompt
    :rtype: str
    """
    serial = console_mgr.get_console(serial_id)
    return serial.read_up_to_prompt(timeout=timeout, internal_timeout=internal_timeout)


def get_output(serial_id):
    """
    Get all accumulated output from the serial console.
    
    :param serial_id: Unique identifier for the serial console
    :type serial_id: str
    :return: All accumulated output from the console
    :rtype: bytes
    """
    serial = console_mgr.get_console(serial_id)
    output = serial.get_output()
    if isinstance(output, str):
        output = output.encode("utf-8", "ignore")
    return output
