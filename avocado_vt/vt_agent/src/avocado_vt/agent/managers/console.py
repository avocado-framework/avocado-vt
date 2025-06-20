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
Console management module for Avocado-VT agent.

This module provides classes and utilities for managing console connections
to virtual machines. It supports different console types such as serial consoles
and provides a unified interface for console operations including creation,
registration, and lifecycle management.

Classes:
    ConsoleError: Base exception for console-related errors
    UnsupportedConsoleTypeError: Exception for unsupported console types
    Console: Base console class that wraps backend console sessions
    SerialConsole: Serial console implementation
    ConsoleManager: Manager for console connections and lifecycle

The module integrates with aexpect for shell session management and provides
logging capabilities for console operations.
"""

import logging
import os

from avocado_vt.agent.core import data_dir
from virttest import utils_logfile

import aexpect

LOG = logging.getLogger("avocado.service." + __name__)


class ConsoleError(Exception):
    """Base exception class for console-related errors."""

    pass


class UnsupportedConsoleTypeError(ConsoleError):
    """Exception raised when an unsupported console type is requested."""

    def __init__(self, console_type):
        """
        Initialize the exception with the unsupported console type.

        :param console_type: The console type that is not supported
        :type console_type: str
        """
        ConsoleError.__init__(self)
        self._console_type = console_type

    def __str__(self):
        """
        Return a string representation of the exception.

        :return: Error message describing the unsupported console type
        :rtype: str
        """
        return f"Unsupported console type: {self._console_type}"


class Console(object):
    """
    Base console class that wraps a backend console session.

    This class provides a unified interface for different types of console
    connections and delegates method calls to the underlying backend.
    """

    def __init__(self, instance_id, console_type, filename, backend):
        """
        Initialize a console instance.

        :param instance_id: Unique identifier for the VM instance
        :type instance_id: str
        :param console_type: Type of console (e.g., 'serial', 'vnc', 'spice')
        :type console_type: str
        :param filename: Path to the console device or socket file
        :type filename: str
        :param backend: The underlying console session object
        :type backend: object
        """
        self._instance_id = instance_id
        self._console_type = console_type
        self._filename = filename
        self._backend = backend

    @property
    def instance_id(self):
        """
        Get the VM instance ID associated with this console.

        :return: The instance ID
        :rtype: str
        """
        return self._instance_id

    @property
    def console_type(self):
        """
        Get the type of this console.

        :return: The console type (e.g., 'serial', 'vnc', 'spice')
        :rtype: str
        """
        return self._console_type

    @property
    def filename(self):
        """
        Get the filename/path of the console device or socket.

        :return: The filename or socket path
        :rtype: str
        """
        return self._filename

    def __getattr__(self, item):
        """
        Delegate attribute access to the underlying backend.

        :param item: The attribute name to access
        :type item: str
        :return: The attribute value from the backend
        :rtype: Any
        """
        return getattr(self._backend, item)

    def close(self):
        """Close the console connection by closing the backend session."""
        self._backend.close()


class SerialConsole(Console):
    """
    Serial console implementation.

    A specialized console class for serial console connections.
    """

    def __init__(self, instance_id, filename, backend):
        """
        Initialize a serial console.

        :param instance_id: Unique identifier for the VM instance
        :type instance_id: str
        :param filename: Path to the serial console socket file
        :type filename: str
        :param backend: The underlying shell session object
        :type backend: object
        """
        super(SerialConsole, self).__init__(instance_id, "serial", filename, backend)


class ConsoleManager(object):
    """
    Manages the connection to the console for the VM
    """

    def __init__(self):
        """Initialize the console manager with an empty console registry."""
        self._consoles = {}

    @staticmethod
    def create_console(name, instance_id, console_type, filename, params):
        """
        Create a new console instance of the specified type.

        :param name: Name identifier for the console
        :type name: str
        :param instance_id: Unique identifier for the VM instance
        :type instance_id: str
        :param console_type: Type of console to create ('serial', 'vnc', 'spice')
        :type console_type: str
        :param filename: Path to the console device or socket file
        :type filename: str
        :param params: Parameters for console configuration
        :type params: dict
        :return: A console instance of the appropriate type
        :rtype: Console
        :raises UnsupportedConsoleTypeError: If the console type is not supported
        :raises ConsoleError: If console creation fails
        """
        try:
            if console_type == "serial":
                log_name = os.path.join(
                    data_dir.get_console_log_dir(),
                    f"{console_type}-{name}-{instance_id}.log",
                )
                serial_session = aexpect.ShellSession(
                    "nc -U %s" % filename,
                    auto_close=False,
                    output_func=utils_logfile.log_line,
                    output_params=(log_name,),
                    prompt=params.get("shell_prompt", "[\#\$]"),
                    status_test_command=params.get("status_test_command", "echo $?"),
                    encoding="UTF-8",
                )
                return SerialConsole(instance_id, filename, serial_session)
            else:
                raise UnsupportedConsoleTypeError(console_type)
        except Exception as e:
            raise ConsoleError(
                f"Failed to create the {console_type} console: {e}"
            ) from e

    def close_console(self, console_id):
        """
        Close a console connection by its ID.

        :param console_id: The unique identifier of the console to close
        :type console_id: str
        :raises ConsoleError: If console with the given ID is not found
        """
        console = self._consoles.get(console_id)
        if console is None:
            LOG.warning(f"Console with ID '{console_id}' not found")
            return

        console.close()

    def register_console(self, console_id, console):
        """
        Register a console instance with the manager.

        :param console_id: Unique identifier for the console
        :type console_id: str
        :param console: The console instance to register
        :type console: Console
        :raises ConsoleError: If a console with the same ID is already registered
        """
        if console_id in self._consoles:
            raise ConsoleError("The console has been registered")
        self._consoles[console_id] = console

    def unregister_console(self, console_id):
        """
        Unregister a console from the manager.

        :param console_id: The unique identifier of the console to unregister
        :type console_id: str
        """
        if console_id in self._consoles:
            del self._consoles[console_id]

    def get_console(self, console_id):
        """
        Retrieve a console instance by its ID.

        :param console_id: The unique identifier of the console
        :type console_id: str
        :return: The console instance if found, None otherwise
        :rtype: Console or None
        """
        return self._consoles.get(console_id)

    def get_consoles_by_instance(self, instance_id, console_type=None):
        """
        Get all consoles associated with a specific VM instance.

        :param instance_id: The VM instance identifier
        :type instance_id: str
        :param console_type: Filter by console type. If None, returns all consoles for the instance
        :type console_type: str or None
        :return: List of console instances matching the criteria
        :rtype: list[Console]
        """
        consoles = []
        for console in self._consoles.values():
            if console.instance_id == instance_id:
                if console_type and console.console_type == console_type:
                    consoles.append(console)
                else:
                    consoles.append(console)

        return consoles
