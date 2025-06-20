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
QEMU connection client driver for Avocado-VT agent.

This module provides functionality for creating connection clients to QEMU
virtual machines. It supports different connection protocols (QMP, HMP) and
backend types (TCP socket, Unix socket) for communicating with QEMU instances.

Functions:
    create_connect_client: Create a connection client for QEMU instances

The module integrates with virttest's monitor client functionality and provides
automatic log file management for connection operations.

Supported Protocols:
    - QMP (QEMU Machine Protocol): JSON-based protocol for machine communication
    - HMP (Human Monitor Protocol): Human-readable command interface

Supported Backends:
    - TCP Socket: Network-based connection using host:port
    - Unix Socket: Local socket file-based connection
"""

import logging
import os

from avocado_vt.agent.core import data_dir
from virttest.vt_monitor import client

LOG = logging.getLogger("avocado.service." + __name__)


def create_connect_client(
    instance_id, instance_pid, name, protocol, client_params, log_file=None
):
    """
    Create a connection client for communicating with a QEMU virtual machine.
    
    This function creates either a QMP (QEMU Machine Protocol) or HMP (Human
    Monitor Protocol) client for connecting to QEMU instances using different
    backend types (TCP or Unix sockets).
    
    :param instance_id: Unique identifier for the VM instance
    :type instance_id: str
    :param instance_pid: Process ID of the QEMU instance
    :type instance_pid: int
    :param name: Name identifier for the connection
    :type name: str
    :param protocol: Protocol to use for communication ('qmp' or 'hmp')
    :type protocol: str
    :param client_params: Parameters for client configuration including backend details
    :type client_params: dict
    :param log_file: Optional path to log file for connection logging
    :type log_file: str or None
    :return: Monitor client instance (QMPMonitor or HumanMonitor)
    :rtype: object
    :raises ValueError: If no address is specified for socket backend
    :raises NotImplementedError: If backend type or protocol is not supported
    
    Expected client_params keys:
        - backend: Backend type ('socket')
        - host: Hostname for TCP socket (required with port)
        - port: Port number for TCP socket (required with host)
        - path: Path for Unix socket (alternative to host/port)
    """
    backend = client_params.get("backend")

    if log_file is None:
        log_file = "%s-instance-%s-pid-%s.log" % (name, instance_id, instance_pid)
        log_file = os.path.join(data_dir.get_console_log_dir(), log_file)

    if backend == "socket":
        host = client_params.get("host")
        port = client_params.get("port")
        path = client_params.get("path")
        if host and port:
            address = (host, port)
            backend_type = "tcp_socket"
        elif path:
            address = path
            backend_type = "unix_socket"
        else:
            raise ValueError("No address specified for connect client")
    else:
        raise NotImplementedError("Not support connect backend type %s" % backend)

    if protocol == "qmp":
        return client.QMPMonitor(instance_id, name, backend_type, address, log_file)
    elif protocol == "hmp":
        return client.HumanMonitor(instance_id, name, backend_type, address, log_file)
    else:
        raise NotImplementedError("Unsupported connect protocol %s" % protocol)
