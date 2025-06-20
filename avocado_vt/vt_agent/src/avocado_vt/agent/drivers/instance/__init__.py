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
Virtual Machine Instance Driver Framework for Avocado-VT Agent.

This module provides the core abstraction layer for managing virtual machine
instances across different hypervisor backends in the Avocado-VT testing
framework. It defines a unified interface that allows the agent to interact
with various virtualization technologies through a consistent API.

Key Components:
    - InstanceDriver: Abstract base class defining the common interface
    - InstanceInfo: Dataclass for storing comprehensive instance metadata
    - InstanceStates: Enumeration of possible VM states
    - Exception classes: Specialized exceptions for different error conditions

Supported Operations:
    - Instance lifecycle management (start, stop, pause, resume)
    - Hot-plug/hot-unplug device operations
    - Process monitoring and status checking
    - Hypervisor capability discovery
    - Serial console management
    - Resource cleanup and management

Architecture:
    The framework follows an abstract factory pattern where concrete
    implementations (e.g., QemuInstanceDriver, LibvirtInstanceDriver)
    inherit from InstanceDriver and provide backend-specific functionality.
    This allows the agent to support multiple hypervisors while maintaining
    a consistent interface for test automation.

Extensibility:
    New hypervisor backends can be added by:
    1. Subclassing InstanceDriver
    2. Implementing all abstract methods
    3. Registering the driver with the instance manager
"""

import glob
import os
import time
from abc import ABCMeta
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional

import six
from avocado_vt.agent.managers import connect_mgr
from virttest import data_dir, utils_misc


class InstanceDriverError(Exception):
    """Base exception for InstanceDriver errors"""

    pass


class InstanceStartError(InstanceDriverError):
    """Exception raised when instance fails to start"""

    pass


class InstanceStopError(InstanceDriverError):
    """Exception raised when instance fails to stop"""

    pass


class DeviceError(InstanceDriverError):
    """Exception raised for device-related operations"""

    pass


class CapabilityError(InstanceDriverError):
    """Exception raised for capability-related operations"""

    pass


class InstanceStates(Enum):
    """
    Enumeration of possible virtual machine instance states.

    This enum defines the complete lifecycle states that a virtual machine
    instance can be in during its operation within the Avocado-VT framework.
    These states are used throughout the instance management system to track
    and validate state transitions.

    States:
        RUNNING: Instance is actively running and executing
        STOPPED: Instance is completely stopped and not consuming resources
        PAUSED: Instance execution is suspended but memory state is preserved
        BUILDING: Instance is being configured/built but not yet started

    State Transitions:
        BUILDING -> RUNNING: Instance starts successfully
        RUNNING -> PAUSED: Instance is paused while running
        PAUSED -> RUNNING: Instance resumes from pause
        RUNNING -> STOPPED: Instance is shut down
        STOPPED -> RUNNING: Instance is restarted
        BUILDING -> STOPPED: Instance build fails or is cancelled
    """

    RUNNING = auto
    STOPPED = auto
    PAUSED = auto
    BUILDING = auto


@dataclass
class InstanceInfo:
    """
    Comprehensive metadata container for virtual machine instances.

    This dataclass stores all relevant information about a VM instance,
    including configuration, runtime state, capabilities, and associated
    resources. Used by InstanceDriver implementations to maintain consistent
    state tracking across different hypervisor backends.

    Attributes:
        uuid (str): Globally unique identifier for the instance
        backend (str): Hypervisor backend type (e.g., 'qemu', 'libvirt')
        spec (dict): Instance specification and configuration parameters
        status (str, optional): Current runtime status. Defaults to None.
        capabilities (set): Set of supported hypervisor capabilities
        cmdline (str, optional): Command line used to start instance. Defaults to None.
        devices (Any, optional): Device configuration and state. Defaults to None.
        process (Any, optional): Associated process information. Defaults to None.
        serials (dict): Serial console configurations and connections
        migrate_incoming (dict, optional): Migration target configuration. Defaults to None.
    """

    uuid: str
    backend: str
    spec: dict
    status: str = None
    capabilities: set = field(default_factory=set)
    cmdline: str = None
    devices: Any = None
    process: Any = None
    serials: dict = field(default_factory=dict)
    migrate_incoming: Optional[dict] = None


@six.add_metaclass(ABCMeta)
class InstanceDriver(object):
    """
    Abstract base class for virtual machine instance drivers.

    This class defines the common interface for managing virtual machine instances
    across different hypervisor backends (e.g., QEMU, KVM, Xen). It provides
    standardized methods for instance lifecycle management, device operations,
    and capability discovery.

    Attributes:
        instance_id (str): Unique identifier for the VM instance
        instance_backend (str): Backend hypervisor type (e.g., 'qemu', 'kvm')
        instance_info (InstanceInfo): Comprehensive instance metadata and state

    Key Responsibilities:
        - Instance lifecycle management (start, stop, pause, resume)
        - Device hot-plug/hot-unplug operations
        - Process and status monitoring
        - Hypervisor capability detection
        - Serial console management
        - Resource cleanup

    Usage:
        Subclasses must implement all abstract methods to provide backend-specific
        functionality. The driver maintains instance state through InstanceInfo
        and provides a consistent interface regardless of the underlying hypervisor.
    """

    def __init__(
        self, instance_id: str, instance_backend: str, instance_info: InstanceInfo
    ) -> None:
        self._uuid = self._generate_unique_id()
        self._instance_id = instance_id
        self._instance_backend = instance_backend
        self.instance_info = instance_info

    @property
    def instance_id(self) -> str:
        """
        Get the unique identifier for this VM instance.

        :return: The instance identifier
        :rtype: str
        """
        return self._instance_id

    @property
    def instance_backend(self) -> str:
        """
        Get the hypervisor backend type for this instance.

        :return: Backend type (e.g., 'qemu', 'libvirt')
        :rtype: str
        """
        return self._instance_backend

    def make_create_cmdline(self):
        """
        Generate the command line for creating/starting the VM instance.

        :return: Complete command line string for hypervisor execution
        :rtype: str
        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def start(self, cmdline, timeout: int = 60) -> bool:
        """
        Start the virtual machine instance using the provided command line.

        :param cmdline: Complete hypervisor command line to execute
        :type cmdline: str
        :param timeout: Maximum time to wait for startup
        :type timeout: int
        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def stop(
        self,
        graceful: bool = True,
        timeout: int = 60,
        shutdown_cmd: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> bool:
        """
        Stop the virtual machine instance with optional graceful shutdown.

        :param graceful: Attempt graceful shutdown first
        :type graceful: bool
        :param timeout: Maximum time to wait for shutdown
        :type timeout: int
        :param shutdown_cmd: Custom shutdown command to send to guest
        :type shutdown_cmd: Optional[str]
        :param username: Guest username for authentication
        :type username: Optional[str]
        :param password: Guest password for authentication
        :type password: Optional[str]
        :param prompt: Expected shell prompt after login
        :type prompt: Optional[str]
        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def pause(self) -> bool:
        """
        Pause the currently running virtual machine instance.

        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def is_paused(self) -> bool:
        """
        Check if the virtual machine instance is currently paused.

        :return: True if instance is paused, False otherwise
        :rtype: bool
        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def resume(self) -> bool:
        """
        Resume a previously paused virtual machine instance.

        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def is_running(self) -> bool:
        """
        Check if the virtual machine instance is currently running.

        :return: True if instance is actively running, False otherwise
        :rtype: bool
        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def get_status(self) -> str:
        """
        Get the current status of the virtual machine instance.

        :return: Current instance state (e.g., 'running', 'stopped', 'paused')
        :rtype: str
        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def get_pid(self, parent_process: Optional[Any] = None) -> Optional[int]:
        """
        Get the process ID of the hypervisor process running this instance.

        :param parent_process: Parent process to search from. If None, searches system-wide
        :type parent_process: Optional[Any]
        :return: Process ID of the hypervisor process
        :rtype: int
        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def get_process_info(self, attr: str) -> Dict[str, Any]:
        """
        Get specific attribute information about processes related to the instance.

        :param attr: The process attribute to retrieve (e.g., 'pid' for process ID,
                     'output' for process output, 'status' for process status).
        :type attr: str
        :return: The requested attribute information of the process.
        :rtype: str
        :raises NotImplementedError: Must be implemented by concrete subclasses.
        """
        raise NotImplementedError

    def get_serial_info(self, serial_id: str, attr: str) -> Any:
        """
        Get specific attribute information about a serial console connection.

        Retrieves detailed information about serial console connections associated
        with the virtual machine instance, such as connection ports, socket paths,
        connection status, or other serial-specific attributes.

        :param serial_id: Unique identifier for the serial console connection
                          (e.g., 'serial0', 'serial1').
        :type serial_id: str
        :param attr: The serial console attribute to retrieve (e.g., 'port' for TCP port,
                     'socket_path' for Unix socket path, 'status' for connection status,
                     'device' for device file path).
        :type attr: str
        :return: Requested serial console attribute information. The type depends on
                 the specific attribute requested (int for ports, str for paths, etc.).
        :rtype: Any
        :raises NotImplementedError: Must be implemented by concrete subclasses.
        """
        raise NotImplementedError

    def attach_device(
        self, device_spec: Dict[str, Any], monitor_id: Optional[str] = None
    ) -> bool:
        """
        Hot-attach a device to the virtual machine instance.

        :param device_spec: Device specification including type, parameters, and configuration
        :type device_spec: Dict[str, Any]
        :param monitor_id: Monitor interface to use for the operation
        :type monitor_id: Optional[str]
        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def detach_device(
        self, device_spec: Dict[str, Any], monitor_id: Optional[str] = None
    ) -> bool:
        """
        Hot-detach a device from the virtual machine instance.

        :param device_spec: Device specification for the device to be removed
        :type device_spec: Dict[str, Any]
        :param monitor_id: Monitor interface to use for the operation
        :type monitor_id: Optional[str]
        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def probe_capabilities(self) -> None:
        """
        Discover and cache the hypervisor's supported capabilities.

        Queries the hypervisor to determine what features and operations
        are supported, updating the instance_info.capabilities set.

        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    def supports_capability(self, capability: str) -> bool:
        """
        Check if a specific capability is supported by this instance.

        :param capability: Name of the capability to check (e.g., 'migration', 'blockdev')
        :type capability: str
        :return: True if capability is supported, False otherwise
        :rtype: bool

        .. note::
            Capabilities must be previously discovered via probe_capabilities()
        """
        return capability in self.instance_info.capabilities

    def cleanup(self, free_mac_addresses: bool = True) -> None:
        """
        Clean up resources associated with this instance.

        Performs cleanup operations including removing temporary files,
        releasing network resources, and optionally freeing MAC addresses.

        :param free_mac_addresses: Whether to release allocated MAC addresses
        :type free_mac_addresses: bool
        :raises NotImplementedError: Must be implemented by concrete subclasses
        """
        raise NotImplementedError

    @staticmethod
    def _generate_unique_id() -> str:
        """
        Generate a unique identifier for this driver
        """
        while True:
            driver_id = time.strftime(
                "%Y%m%d-%H%M%S-"
            ) + utils_misc.generate_random_string(8)
            if not glob.glob(os.path.join(data_dir.get_tmp_dir(), "*%s" % driver_id)):
                return driver_id
