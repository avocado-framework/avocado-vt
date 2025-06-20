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
Virtual Machine Manager (VMM) module for Avocado-VT agent.

This module provides core Virtual Machine Manager functionality for managing
virtual machine instances in an Avocado-VT testing environment. It supports
multiple virtualization backends (QEMU and libvirt) and provides a unified
interface for instance lifecycle management, device operations, and state
management.

Key Components:
    - VirtualMachinesManager: Main class for managing VM instances
    - VMMError: Base exception class for VMM-related errors
    - Instance driver factories: Functions to create backend-specific drivers

Supported Backends:
    - qemu: Direct QEMU instance management
    - libvirt: Libvirt-based instance management
"""

import copy
import logging
import os
import pickle

from avocado_vt.agent.drivers.instance import InstanceStates
from avocado_vt.agent.drivers.instance.libvirt import (
    LibvirtInstanceDriver,
    LibvirtInstanceInfo,
)
from avocado_vt.agent.drivers.instance.qemu import QemuInstanceDriver, QemuInstanceInfo

LOG = logging.getLogger("avocado.service." + __name__)


class VMMError(Exception):
    """
    Base exception class for Virtual Machine Manager errors.

    Raised when VMM operations fail due to invalid states, missing resources,
    or other VMM-specific error conditions.
    """

    pass


class UnsupportedInstanceBackend(VMMError):
    """
    Exception raised when an unsupported virtualization backend is requested.

    :param backend: The name of the unsupported backend.
    :type backend: str
    """

    def __init__(self, backend):
        self._backend = backend
        super().__init__(f"Unsupported instance backend: {self._backend}")

    def __str__(self):
        return f"Unsupported instance backend: {self._backend}"


def get_instance_info(instance_id, instance_backend, instance_spec):
    """
    Create and return an instance info object for the specified backend.

    :param instance_id: Unique identifier for the VM instance.
    :type instance_id: str
    :param instance_backend: Backend type ('qemu' or 'libvirt').
    :type instance_backend: str
    :param instance_spec: Specification dictionary containing instance configuration.
    :type instance_spec: dict
    :return: Backend-specific instance info object.
    :rtype: InstanceInfo
    :raises UnsupportedInstanceBackend: If the specified backend is not supported.
    """
    _instance_info_backends = {
        "qemu": QemuInstanceInfo,
        "libvirt": LibvirtInstanceInfo,
    }

    if instance_backend not in _instance_info_backends:
        raise UnsupportedInstanceBackend(instance_backend)

    return _instance_info_backends.get(instance_backend)(
        instance_id, instance_backend, instance_spec
    )


def get_instance_driver(instance_id, instance_backend, instance_info):
    """
    Create and return an instance driver for the specified backend.

    :param instance_id: Unique identifier for the VM instance.
    :type instance_id: str
    :param instance_backend: Backend type ('qemu' or 'libvirt').
    :type instance_backend: str
    :param instance_info: Instance information object.
    :type instance_info: InstanceInfo
    :return: Backend-specific instance driver object.
    :rtype: InstanceDriver
    :raises UnsupportedInstanceBackend: If the specified backend is not supported.
    """
    _backend_drivers = {
        "qemu": QemuInstanceDriver,
        "libvirt": LibvirtInstanceDriver,
    }

    if instance_backend not in _backend_drivers:
        raise UnsupportedInstanceBackend(instance_backend)

    return _backend_drivers.get(instance_backend)(instance_id, instance_info)


class VirtualMachinesManager(object):
    """
    Virtual Machine Manager for local instance resource management.

    This class provides a unified interface for managing virtual machine instances
    across different virtualization backends. It handles instance registration,
    lifecycle management, device operations, and state persistence.

    The manager maintains instance information in a persistent file and manages
    driver instances for efficient resource utilization.

    Attributes:
        _filename (str): Path to the persistent instance storage file.
        _drivers (dict): Cache of active instance drivers.
    """

    def __init__(self):
        """
        Initialize the Virtual Machines Manager.

        Sets up the persistent storage path and initializes the driver cache.
        The default storage location is '/var/lib/vt_agent/instances'.
        """
        self._filename = "/var/lib/vt_agent/instances"
        self._drivers = {}

    @property
    def instances(self):
        """
        Get all registered instances from persistent storage.

        :return: Dictionary mapping instance IDs to instance information objects.
                 Returns empty dict if no instances are registered.
        :rtype: dict
        """
        return self._load_instances()

    def get_instance_info(self, instance_id):
        """
        Retrieve information for a specific instance.

        :param instance_id: Unique identifier of the instance.
        :type instance_id: str
        :return: Instance information object containing configuration,
                 state, and runtime details.
        :rtype: InstanceInfo
        :raises VMMError: If the instance is not found.
        """
        instance_info = self.instances.get(instance_id)
        if not instance_info:
            raise VMMError(f"Instance {instance_id} not found")
        return instance_info

    def get_driver(self, instance_id):
        """
        Get or create a driver instance for the specified VM.

        This method implements driver caching - it returns an existing driver
        if available, or creates a new one. The driver's instance info is
        always updated to reflect the current state.

        :param instance_id: Unique identifier of the instance.
        :type instance_id: str
        :return: Backend-specific driver for the instance.
        :rtype: InstanceDriver
        :raises VMMError: If the instance is not found or driver creation fails.
        """
        if not self._drivers.get(instance_id):
            instance_info = self.get_instance_info(instance_id)
            if instance_info:
                instance_backend = instance_info.backend
                instance_driver = get_instance_driver(
                    instance_id, instance_backend, instance_info
                )
                self._drivers[instance_id] = instance_driver
                return instance_driver
            raise VMMError(f"Failed to get the driver for {instance_id}")

        else:
            instance_driver = self._drivers[instance_id]
            latest_instance_info = self.get_instance_info(instance_id)
            if latest_instance_info:
                instance_driver.instance_info = latest_instance_info
            return instance_driver

    def _save_instances(self, instances):
        """
        Save instances data to persistent storage.

        :param instances: Dictionary of instance data to save.
        :type instances: dict
        """
        dirname = os.path.dirname(self._filename)
        if not os.path.isdir(dirname):
            os.makedirs(dirname, exist_ok=True)

        with open(self._filename, "wb") as f:
            pickle.dump(instances, f, protocol=0)

    def _load_instances(self):
        """
        Load instances data from persistent storage.

        :return: Dictionary of instance data, empty dict if file doesn't exist.
        :rtype: dict
        """
        if os.path.exists(self._filename):
            with open(self._filename, "rb") as instances:
                return pickle.load(instances)
        LOG.warning("Instance environment file not found")
        return {}

    def register_instance(self, instance_id, instance_info):
        """
        Register an instance in the manager.

        :param instance_id: Unique identifier for the instance.
        :type instance_id: str
        :param instance_info: Instance information object.
        :type instance_info: InstanceInfo
        :raises VMMError: If the instance is already registered.
        """
        if instance_id in self.instances:
            raise VMMError(f"The instance {instance_id} is already registered")

        instance = copy.deepcopy(self.instances)
        instance[instance_id] = instance_info
        self._save_instances(instance)

    def unregister_instance(self, instance_id):
        """
        Unregister an instance from the manager.

        :param instance_id: Unique identifier of the instance to unregister.
        :type instance_id: str
        :raises VMMError: If the instance is not registered.
        """
        instance = copy.deepcopy(self.instances)

        if instance_id in copy.deepcopy(self.instances):
            del instance[instance_id]
            self._save_instances(instance)
        else:
            raise VMMError(f"The instance {instance_id} is not registered")

    def update_instance(self, instance_id, instance_info):
        """
        Update instance information in persistent storage.

        :param instance_id: Unique identifier of the instance.
        :type instance_id: str
        :param instance_info: Updated instance information object.
        :type instance_info: InstanceInfo
        """
        instances = copy.deepcopy(self.instances)
        instances[instance_id] = instance_info
        self._save_instances(instances)

    def build_instance(
        self, instance_id, instance_backend, instance_spec, migrate_incoming=None
    ):
        """
        Build an instance configuration without starting it.

        Creates the instance info object, probes capabilities, and generates
        the command line for starting the instance.

        :param instance_id: Unique identifier for the instance.
        :type instance_id: str
        :param instance_backend: Backend type ('qemu' or 'libvirt').
        :type instance_backend: str
        :param instance_spec: Instance specification dictionary.
        :type instance_spec: dict
        :param migrate_incoming: Migration configuration for incoming migration.
        :type migrate_incoming: dict or None
        :return: Configured instance information object.
        :rtype: InstanceInfo
        :raises VMMError: If the instance has already been built.
        :raises UnsupportedInstanceBackend: If the backend is not supported.
        """
        if instance_id in self.instances:
            raise VMMError(f"The instance {instance_id} has been built")

        instance_info = get_instance_info(instance_id, instance_backend, instance_spec)
        instance_driver = get_instance_driver(
            instance_id, instance_backend, instance_info
        )
        instance_info.capabilities = instance_driver.probe_capabilities()

        if migrate_incoming:
            instance_info.migrate_incoming = migrate_incoming

        instance_info.cmdline = instance_driver.make_create_cmdline()
        instance_info.status = InstanceStates.BUILDING

        self._drivers[instance_id] = instance_driver
        return instance_info

    def run_instance(self, instance_id):
        """
        Start a built instance.

        The instance must be in BUILDING or STOPPED state to be started.

        :param instance_id: Unique identifier of the instance to start.
        :type instance_id: str
        :raises VMMError: If the instance is not in BUILDING or STOPPED state.
        """
        instance_info = self.get_instance_info(instance_id)
        if instance_info.status not in (
            InstanceStates.BUILDING,
            InstanceStates.STOPPED,
        ):
            raise VMMError(f"The instance {instance_id} is not building or stopped")

        instance_driver = self.get_driver(instance_id)
        instance_info.process = instance_driver.start(instance_info.cmdline)
        instance_info.status = InstanceStates.RUNNING
        self.update_instance(instance_id, instance_info)

    def attach_instance_device(self, instance_id, device_spec, monitor_id=None):
        """
        Attach a device to an instance.

        :param instance_id: The ID of the instance to attach the device to.
        :type instance_id: str
        :param device_spec: The specification of the device to attach.
        :type device_spec: dict
        :param monitor_id: The ID of the monitor to use.
        :type monitor_id: str or None
        :return: The result of the device attachment.
        :rtype: tuple
        """
        instance_info = self.get_instance_info(instance_id)
        if instance_info.status not in (
            InstanceStates.BUILDING,
            InstanceStates.RUNNING,
            InstanceStates.PAUSED,
        ):
            raise VMMError(
                f"The instance {instance_id} is not building or running or paused"
            )

        instance_driver = self.get_driver(instance_id)
        out, ret = instance_driver.attach_device(device_spec, monitor_id)
        self.update_instance(instance_id, instance_driver.instance_info)
        return out, ret

    def detach_instance_device(self, instance_id, dev_spec, monitor_id=None):
        """
        Detach a device from an instance.

        :param instance_id: The ID of the instance to detach the device from.
        :type instance_id: str
        :param dev_spec: The specification of the device to detach.
        :type dev_spec: dict
        :param monitor_id: The ID of the monitor to use.
        :type monitor_id: str or None
        :return: The result of the device detachment.
        :rtype: tuple
        """
        instance_info = self.get_instance_info(instance_id)
        if instance_info.status not in (
            InstanceStates.BUILDING,
            InstanceStates.RUNNING,
            InstanceStates.PAUSED,
        ):
            raise VMMError(
                f"The instance {instance_id} is not building or running or paused"
            )

        instance_driver = self.get_driver(instance_id)
        out, ret = instance_driver.detach_device(dev_spec, monitor_id)
        self.update_instance(instance_id, instance_driver.instance_info)
        return out, ret

    def get_instance_pid(self, instance_id):
        """
        Get the process ID of the instance.

        :param instance_id: Unique identifier of the instance.
        :type instance_id: str
        :return: Process ID of the instance, or None if the instance is not running.
        :rtype: int or None
        :note: Returns the PID of the parent shell process for the instance.
        """
        instance_driver = self.get_driver(instance_id)
        return instance_driver.get_pid()

    def stop_instance(
        self,
        instance_id,
        graceful=True,
        timeout=60,
        shutdown_cmd=None,
        username=None,
        password=None,
        prompt=None,
    ):
        """
        Stop a running instance.

        The instance must be in RUNNING or PAUSED state to be stopped.

        :param instance_id: The ID of the instance to stop.
        :type instance_id: str
        :param graceful: Whether to stop the instance gracefully.
        :type graceful: bool
        :param timeout: Timeout in seconds for the stop operation.
        :type timeout: int
        :param shutdown_cmd: Custom shutdown command to use.
        :type shutdown_cmd: str or None
        :param username: Username for guest shutdown (if graceful).
        :type username: str or None
        :param password: Password for guest shutdown (if graceful).
        :type password: str or None
        :param prompt: Expected prompt for guest shutdown (if graceful).
        :type prompt: str or None
        :raises VMMError: If the instance is not in RUNNING or PAUSED state.
        """
        instance_info = self.get_instance_info(instance_id)
        if instance_info.status not in (InstanceStates.RUNNING, InstanceStates.PAUSED):
            raise VMMError(f"The instance {instance_id} is not running or paused")

        instance_driver = self.get_driver(instance_id)
        instance_driver.stop(
            graceful, timeout, shutdown_cmd, username, password, prompt
        )
        instance_info.status = InstanceStates.STOPPED
        self.update_instance(instance_id, instance_info)

    def pause_instance(self, instance_id):
        """
        Pause a running instance.

        The instance must be in RUNNING state to be paused.

        :param instance_id: The ID of the instance to pause.
        :type instance_id: str
        :raises VMMError: If the instance is not in RUNNING state.
        """
        instance_info = self.get_instance_info(instance_id)
        if instance_info.status not in (InstanceStates.RUNNING,):
            raise VMMError(f"The instance {instance_id} is not running")

        instance_driver = self.get_driver(instance_id)
        instance_driver.pause()
        instance_info.status = InstanceStates.PAUSED
        self.update_instance(instance_id, instance_info)

    def is_instance_paused(self, instance_id):
        """
        Check if an instance is paused.

        :param instance_id: The ID of the instance to check.
        :type instance_id: str
        :return: True if the instance is paused, False otherwise.
        :rtype: bool
        """
        instance_driver = self.get_driver(instance_id)
        return instance_driver.is_paused()

    def resume_instance(self, instance_id):
        """
        Resume a paused instance.

        The instance must be in PAUSED state to be resumed.

        :param instance_id: The ID of the instance to resume.
        :type instance_id: str
        :raises VMMError: If the instance is not in PAUSED state.
        """
        instance_info = self.get_instance_info(instance_id)
        if instance_info.status not in (InstanceStates.PAUSED,):
            raise VMMError(f"The instance {instance_id} is not paused")

        instance_driver = self.get_driver(instance_id)
        instance_driver.resume()
        instance_info.status = InstanceStates.RUNNING
        self.update_instance(instance_id, instance_info)

    def is_instance_running(self, instance_id):
        """
        Check if an instance is running.

        :param instance_id: The ID of the instance to check.
        :type instance_id: str
        :return: True if the instance is running, False otherwise.
        :rtype: bool
        """
        instance_driver = self.get_driver(instance_id)
        return instance_driver.is_running()

    def get_instance_process_info(self, instance_id, attr):
        """
        Get information about a process running on an instance.

        :param instance_id: The ID of the instance.
        :type instance_id: str
        :param attr: The attribute of the process to get information about.
        :type attr: str
        :return: Information about the process.
        :rtype: dict
        """
        instance_driver = self.get_driver(instance_id)
        return instance_driver.get_process_info(attr)

    def cleanup_instance(self, instance_id, free_mac_addresses=True):
        """
        Clean up an instance.

        :param instance_id: The ID of the instance to clean up.
        :type instance_id: str
        :param free_mac_addresses: Whether to free the MAC addresses of the instance.
        :type free_mac_addresses: bool
        """
        instance_driver = self.get_driver(instance_id)
        instance_driver.cleanup(free_mac_addresses)

    def check_instance_capability(self, instance_id, capability):
        """
        Check if an instance has a capability.

        :param instance_id: The ID of the instance to check.
        :type instance_id: str
        :param capability: The capability to check for.
        :type capability: str
        :return: True if the instance has the capability, False otherwise.
        :rtype: bool
        """
        instance_driver = self.get_driver(instance_id)
        return instance_driver.supports_capability(capability)

    def check_instance_migration_parameter(self, instance_id, parameter):
        """
        Check if an instance has a migration parameter.

        :param instance_id: The ID of the instance to check.
        :type instance_id: str
        :param parameter: The migration parameter to check for.
        :type parameter: str
        :return: True if the instance has the migration parameter, False otherwise.
        :rtype: bool
        """
        instance_driver = self.get_driver(instance_id)
        return instance_driver.supports_capability(parameter)
