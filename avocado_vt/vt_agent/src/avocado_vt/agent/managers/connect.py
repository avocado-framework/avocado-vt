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
Connection management module for Avocado-VT agent.

This module provides classes and utilities for managing connections to
virtual machine instances. It supports different connection backends
and protocols, providing a unified interface for connection operations
including creation, registration, and lifecycle management.

Classes:
    ConnectError: Base exception for connection-related errors
    UnsupportedConnectBackendTypeError: Exception for unsupported backend types
    ConnectManager: Manager for connection instances and lifecycle

The module currently supports QEMU backend connections and can be extended
to support additional virtualization backends.
"""

import logging

from avocado_vt.agent.drivers.connect_client import qemu

LOG = logging.getLogger("avocado.service." + __name__)


class ConnectError(Exception):
    """Base exception class for connection-related errors."""
    pass


class UnsupportedConnectBackendTypeError(ConnectError):
    """Exception raised when an unsupported connection backend type is requested."""
    
    def __init__(self, connect_type):
        """
        Initialize the exception with the unsupported connection type.
        
        :param connect_type: The connection backend type that is not supported
        :type connect_type: str
        """
        ConnectError.__init__(self)
        self._connect_type = connect_type

    def __str__(self):
        """
        Return a string representation of the exception.
        
        :return: Error message describing the unsupported connection type
        :rtype: str
        """
        return f"Unsupported connect type: {self._connect_type}"


class ConnectManager(object):
    """
    Manages connections to virtual machine instances.
    
    This class provides a centralized way to create, register, and manage
    connections to virtual machines using different backend types and protocols.
    """
    
    def __init__(self):
        """Initialize the connection manager with an empty connection registry."""
        self._connects = {}

    @staticmethod
    def create_connect(
        instance_id,
        instance_pid,
        instance_backend,
        name,
        protocol,
        params,
        log_file=None,
    ):
        """
        Create a new connection client for a virtual machine instance.
        
        :param instance_id: Unique identifier for the VM instance
        :type instance_id: str
        :param instance_pid: Process ID of the VM instance
        :type instance_pid: int
        :param instance_backend: Backend type for the VM (e.g., 'qemu')
        :type instance_backend: str
        :param name: Name identifier for the connection
        :type name: str
        :param protocol: Protocol to use for the connection
        :type protocol: str
        :param params: Parameters for connection configuration
        :type params: dict
        :param log_file: Optional log file path for connection logging
        :type log_file: str or None
        :return: A connection client instance
        :rtype: object
        :raises UnsupportedConnectBackendTypeError: If the backend type is not supported
        """
        if instance_backend == "qemu":
            connect = qemu.create_connect_client(
                instance_id, instance_pid, name, protocol, params, log_file=log_file
            )
            return connect
        else:
            raise UnsupportedConnectBackendTypeError(instance_backend)

    def register_connect(self, connect_id, connect):
        """
        Register a connection instance with the manager.
        
        :param connect_id: Unique identifier for the connection
        :type connect_id: str
        :param connect: The connection instance to register
        :type connect: object
        :raises ConnectError: If a connection with the same ID is already registered
        """
        if connect_id in self._connects:
            raise ConnectError(f"The connect {connect_id} has been registered")
        self._connects[connect_id] = connect

    def unregister_connect(self, connect_id):
        """
        Unregister a connection from the manager.
        
        :param connect_id: The unique identifier of the connection to unregister
        :type connect_id: str
        """
        if connect_id in self._connects:
            LOG.info(f"Unregistering connection {connect_id}")
            del self._connects[connect_id]
        else:
            LOG.warning(f"Attempted to unregister non-existent connection {connect_id}")

    def get_connect(self, connect_id):
        """
        Retrieve a connection instance by its ID.
        
        :param connect_id: The unique identifier of the connection
        :type connect_id: str
        :return: The connection instance if found, None otherwise
        :rtype: object or None
        """
        return self._connects.get(connect_id)

    def get_connects_by_instance(self, instance_id):
        """
        Get all connections associated with a specific VM instance.
        
        :param instance_id: The VM instance identifier
        :type instance_id: str
        :return: List of connection instances for the specified instance
        :rtype: list
        """
        connects = []
        for connect in self._connects.values():
            if connect.instance_id == instance_id:
                connects.append(connect)

        return connects
