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
Virtual machine connection management service.

This module provides functions for creating, managing, and interacting with
connections to virtual machine instances. It supports various connection
protocols and handles connection lifecycle operations including creation,
data execution, event management, and cleanup.
"""

import json
import logging

from avocado_vt.agent.managers import connect_mgr, vmm
from virttest import utils_misc
from virttest.qemu_devices import qdevices
from virttest.vt_monitor import client

VMM = vmm.VirtualMachinesManager()
LOG = logging.getLogger("avocado.service." + __name__)


def create_connect(instance_id, name, protocol, log_file=None):
    """
    Create a connection to a virtual machine instance.

    :param instance_id: Unique identifier for the VM instance
    :type instance_id: str
    :param name: Name of the connection/device to connect to
    :type name: str
    :param protocol: Protocol to use for the connection
    :type protocol: str
    :param log_file: Path to log file for connection logging
    :type log_file: str or None
    :returns: Unique connection ID for the created connection
    :rtype: str
    :raises ValueError: If client parameters for the specified name are not found
    :raises NotImplementedError: If the instance backend is not supported
    """
    instance_info = VMM.get_instance_info(instance_id)
    instance_backend = instance_info.backend
    devices = instance_info.devices

    if instance_backend == "qemu":
        for device in devices:
            if isinstance(device, qdevices.CharDevice):
                if name in device.get_qid():  # FIXME:
                    client_params = device.params
                    break
        else:
            raise ValueError(f"Not found the qemu client params for {name}")
        instance_pid = VMM.get_instance_pid(instance_id)
        connect = connect_mgr.create_connect(
            instance_id, instance_pid, "qemu", name, protocol, client_params, log_file
        )
        connect_id = utils_misc.generate_random_string(16)
        connect_mgr.register_connect(connect_id, connect)
        return connect_id
    else:
        raise NotImplementedError(
            f"Unsupported the instance backend {instance_backend}"
        )


def is_connected(instance_id, name):
    """
    Check if a connection with the specified name exists for a VM instance.

    :param instance_id: Unique identifier for the VM instance
    :type instance_id: str
    :param name: Name of the connection to check
    :type name: str
    :returns: True if a connection with the specified name exists, False otherwise
    :rtype: bool
    """
    connects = connect_mgr.get_connects_by_instance(instance_id)
    for connect in connects:
        if connect.name == name:
            return True
    return False


def close_connect(connect_id):
    """
    Close and unregister a connection.

    :param connect_id: Unique identifier of the connection to close
    :type connect_id: str
    """
    connect = connect_mgr.get_connect(connect_id)
    if connect:
        connect.close()
        connect_mgr.unregister_connect(connect_id)


def execute_connect_data(
    connect_id, data, timeout=None, debug=False, fd=None, data_format=None
):
    """
    Execute data through a connection.

    :param connect_id: Unique identifier of the connection
    :type connect_id: str
    :param data: Data to execute through the connection
    :param timeout: Timeout in seconds for the operation
    :type timeout: int or None
    :param debug: Enable debug mode. Defaults to False
    :type debug: bool
    :param fd: File descriptor for the operation
    :param data_format: Format of the data
    :type data_format: str or None
    :returns: The result of the data execution. For QMP monitors,
              returns JSON-serialized data to workaround XML-RPC limits.
    """
    connect = connect_mgr.get_connect(connect_id)
    ret = connect.execute_data(data, timeout, debug, fd, data_format)
    # FIXME: Serialize the dict contents to workaround
    #  the OverflowError: int exceeds XML-RPC limits
    if isinstance(connect, client.QMPMonitor):
        ret = json.dumps(ret)
    return ret


def get_connect_events(connect_id):
    """
    Get all events from a connection.

    :param connect_id: Unique identifier of the connection
    :type connect_id: str
    :returns: Events from the connection
    """
    connect = connect_mgr.get_connect(connect_id)
    return connect.get_events()


def get_connect_event(connect_id, name):
    """
    Get a specific event by name from a connection.

    :param connect_id: Unique identifier of the connection
    :type connect_id: str
    :param name: Name of the event to retrieve
    :type name: str
    :returns: The specified event from the connection
    """
    connect = connect_mgr.get_connect(connect_id)
    return connect.get_event(name)


def clear_connect_events(connect_id):
    """
    Clear all events from a connection.

    :param connect_id: Unique identifier of the connection
    :type connect_id: str
    :returns: Result of clearing all events
    """
    connect = connect_mgr.get_connect(connect_id)
    return connect.clear_events()


def clear_connect_event(connect_id, name):
    """
    Clear a specific event by name from a connection.

    :param connect_id: Unique identifier of the connection
    :type connect_id: str
    :param name: Name of the event to clear
    :type name: str
    :returns: Result of clearing the specified event
    """
    connect = connect_mgr.get_connect(connect_id)
    return connect.clear_event(name)
