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
Virtual Machine Manager (VMM) Service Module.

This module provides high-level service functions for managing virtual machine instances
in the Avocado-VT virtualization testing framework. It acts as a wrapper around the
underlying Virtual Machines Manager, providing standardized interface for VM lifecycle
management, device operations, and migration functionality.

The module supports various hypervisors through pluggable backends and provides
comprehensive migration capabilities for testing multi-host virtualization scenarios.

Key functionalities:
- VM instance lifecycle management (build, run, stop, pause, continue)
- Device hotplug/hot-unplug operations
- Live migration operations (prepare, perform, query, finish, confirm, cancel, resume)
- Process and capability management
- Resource cleanup and management

All functions in this module are designed to be called by the Avocado-VT agent
service layer and handle JSON serialization/deserialization for complex parameters.
"""

import json
import logging
import re

from avocado_vt.agent.drivers import migration as migration_drivers
from avocado_vt.agent.managers import vmm

VMM = vmm.VirtualMachinesManager()

LOG = logging.getLogger("avocado.service." + __name__)


def build_instance(instance_id, instance_backend, instance_spec, migrate_incoming=None):
    """
    Builds and registers a new virtual machine instance.

    :param instance_id: A unique identifier for the instance.
    :type instance_id: str
    :param instance_backend: The backend driver to be used for the instance
                             (e.g., 'qemu', 'libvirt').
    :type instance_backend: str
    :param instance_spec: A JSON string containing the instance's configuration
                          dictionary with VM specs such as CPU, memory, disks,
                          networks, and other hypervisor-specific settings.
    :type instance_spec: str
    :param migrate_incoming: Configuration dictionary for incoming migration
                             containing connection details. Expected keys:
                             "uri" (full migration URI), "address" (host/IP),
                             "protocol" (e.g., "tcp", "unix"), "port" (port number).
                             Used when building an instance that will receive a
                             migrated VM. Defaults to None.
    :type migrate_incoming: dict, optional
    :raises vmm.VMMError: If an instance with the given ID is already registered.
    """
    if instance_id in VMM.instances:
        raise vmm.VMMError(f"The instance {instance_id} was registered.")

    instance_spec = json.loads(instance_spec)
    instance_info = VMM.build_instance(
        instance_id, instance_backend, instance_spec, migrate_incoming
    )
    VMM.register_instance(instance_id, instance_info)


def run_instance(instance_id):
    """
    Starts a pre-built virtual machine instance.

    :param instance_id: The unique identifier of the instance to run.
    :type instance_id: str
    """
    VMM.run_instance(instance_id)


def stop_instance(
    instance_id,
    graceful=True,
    timeout=120,
    shutdown_cmd=None,
    username=None,
    password=None,
    prompt=None,
):
    """
    Stops a running virtual machine instance.

    :param instance_id: The unique identifier of the instance to stop.
    :type instance_id: str
    :param graceful: Whether to attempt a graceful shutdown via guest OS.
                     If False, forces immediate termination. Defaults to True.
    :type graceful: bool, optional
    :param timeout: The timeout in seconds for the stop operation. Defaults to 120.
    :type timeout: int, optional
    :param shutdown_cmd: The command to execute in the guest for graceful shutdown
                         (e.g., 'shutdown -h now'). Defaults to None.
    :type shutdown_cmd: str, optional
    :param username: The username for guest authentication during graceful shutdown.
                     Defaults to None.
    :type username: str, optional
    :param password: The password for guest authentication during graceful shutdown.
                     Defaults to None.
    :type password: str, optional
    :param prompt: A regex pattern for the expected shell prompt when connecting
                   to guest. Defaults to None.
    :type prompt: str, optional
    """
    prompt = re.compile(prompt)
    VMM.stop_instance(
        instance_id, graceful, timeout, shutdown_cmd, username, password, prompt
    )


def pause_instance(instance_id):
    """
    Pauses a running virtual machine instance.

    :param instance_id: The unique identifier of the instance to pause.
    :type instance_id: str
    """
    VMM.pause_instance(instance_id)


def continue_instance(instance_id):
    """
    Resumes (continues) a paused virtual machine instance.

    :param instance_id: The unique identifier of the instance to continue.
    :type instance_id: str
    """
    VMM.resume_instance(instance_id)


def get_instance_process_info(instance_id, attr):
    """
    Gets specific attribute information about a process related to the instance.

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param attr: The process attribute to retrieve (e.g., 'pid' for process ID,
                 'output' for process output).
    :type attr: str
    :return: The requested attribute information of the process.
    :rtype: str
    """
    return VMM.get_instance_process_info(instance_id, attr)


def cleanup_instance(instance_id, free_mac_addresses=True):
    """
    Cleans up and unregisters an instance. This typically involves
    removing any leftover resources associated with the instance.

    :param instance_id: The unique identifier of the instance to clean up.
    :type instance_id: str
    :param free_mac_addresses: Whether to release the MAC addresses
                               associated with the instance. Defaults to True.
    :type free_mac_addresses: bool, optional
    """
    VMM.cleanup_instance(instance_id, free_mac_addresses)
    VMM.unregister_instance(instance_id)


def get_instance_pid(instance_id):
    """
    Gets the process ID (PID) of the main instance process.

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :return: The process ID of the instance.
    :rtype: int
    """
    return VMM.get_instance_pid(instance_id)


def attach_instance_device(instance_id, device_spec, monitor_id=None):
    """
    Attaches a device to a running instance (hotplug).

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param device_spec: A JSON string describing the device to attach, including
                        device type, properties, and connection details
                        (e.g., disk, network interface, USB device).
    :type device_spec: str
    :param monitor_id: The ID of the monitor to use for the operation.
    :type monitor_id: str, optional
    :return: The result of the device attachment operation.
    :rtype: tuple[str, bool]
    """
    device_spec = json.loads(device_spec)
    return VMM.attach_instance_device(instance_id, device_spec, monitor_id)


def detach_instance_device(instance_id, device_spec, monitor_id=None):
    """
    Detaches a device from a running instance (hot-unplug).

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param device_spec: A JSON string describing the device to detach, including
                        device ID or identification details to locate the specific
                        device.
    :type device_spec: str
    :param monitor_id: The ID of the monitor to use for the operation.
    :type monitor_id: str, optional
    :return: The result of the device detachment operation.
    :rtype: tuple[str, bool]
    """
    device_spec = json.loads(device_spec)
    return VMM.detach_instance_device(instance_id, device_spec, monitor_id)


def check_instance_capability(instance_id, capability):
    """
    Checks if the instance hypervisor supports a given capability.

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param capability: The name of the capability to check.
    :type capability: str
    :return: True if the capability is supported, False otherwise.
    :rtype: bool
    """
    return VMM.check_instance_capability(instance_id, capability)


def check_instance_migration_parameter(instance_id, parameter):
    """
    Checks a specific migration parameter for the instance.

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param parameter: The name of the migration parameter to check.
    :type parameter: str
    :return: True if the parameter is supported, False otherwise.
    :rtype: bool
    """
    return VMM.check_instance_migration_parameter(instance_id, parameter)


def prepare_migrate_instance(instance_id, instance_backend, instance_spec, mig_params):
    """
    Prepares the system for an instance migration.

    :param instance_id: The unique identifier of the instance to migrate.
    :type instance_id: str
    :param instance_backend: The backend driver to be used for the instance
                             (e.g., 'qemu', 'libvirt').
    :type instance_backend: str
    :param instance_spec: A JSON string containing the instance's configuration
                          dictionary with VM specs such as CPU, memory, disks,
                          networks, and other hypervisor-specific settings.
    :type instance_spec: str
    :param mig_params: A dictionary of migration parameters such as bandwidth
                       limits, downtime tolerance, and compression settings.
    :type mig_params: dict
    :return: The result of the migration preparation, including any setup information
             needed for the migration.
    :rtype: dict
    """
    mig_drv = migration_drivers.get_migration_driver(instance_backend)
    instance_spec = json.loads(instance_spec)
    return mig_drv.prepare_migrate_instance(
        instance_id, instance_backend, instance_spec, mig_params
    )


def perform_migrate_instance(instance_id, mig_params):
    """
    Performs the migration of an instance from the source host.

    :param instance_id: The unique identifier of the instance to migrate.
    :type instance_id: str
    :param mig_params: A dictionary of migration parameters.
    :type mig_params: dict
    :return: The result of the migration operation.
    :rtype: tuple[bool, str]
    """
    instance_info = VMM.get_instance_info(instance_id)
    mig_drv = migration_drivers.get_migration_driver(instance_info.backend)
    return mig_drv.perform_migrate_instance(instance_id, mig_params)


def query_migrate_instance(instance_id):
    """
    Queries the status of an ongoing migration.

    :param instance_id: The unique identifier of the migrating instance.
    :type instance_id: str
    :return: A tuple containing migration status (e.g., 'active', 'completed',
             'failed') and details dictionary with progress information.
    :rtype: tuple[bool, str]
    """
    instance_info = VMM.get_instance_info(instance_id)
    mig_drv = migration_drivers.get_migration_driver(instance_info.backend)
    return mig_drv.query_migrate_instance(instance_id)


def finish_migrate_instance(instance_id, mig_ret, mig_params):
    """
    Finishes the migration process on the destination host.

    :param instance_id: The unique identifier of the migrated instance.
    :type instance_id: str
    :param mig_ret: The return value from the migration perform step.
    :type mig_ret: any
    :param mig_params: A dictionary of migration parameters.
    :type mig_params: dict
    :return: The result of the finalization step.
    :rtype: tuple[bool, str]
    """
    instance_info = VMM.get_instance_info(instance_id)
    mig_drv = migration_drivers.get_migration_driver(instance_info.backend)
    return mig_drv.finish_migrate_instance(instance_id, mig_ret, mig_params)


def confirm_migrate_instance(instance_id, inmig_ret, mig_params):
    """
    Confirms a completed migration on the source host.

    :param instance_id: The unique identifier of the migrated instance.
    :type instance_id: str
    :param inmig_ret: The return value from the incoming migration process.
    :type inmig_ret: any
    :param mig_params: A dictionary of migration parameters.
    :type mig_params: dict
    """
    instance_info = VMM.get_instance_info(instance_id)
    mig_drv = migration_drivers.get_migration_driver(instance_info.backend)
    mig_drv.confirm_migrate_instance(instance_id, inmig_ret, mig_params)


def cancel_migrate_instance(instance_id):
    """
    Cancels an ongoing instance migration.

    :param instance_id: The unique identifier of the instance whose migration
                        should be canceled.
    :type instance_id: str
    :return: The result of the cancellation operation.
    :rtype: bool
    """
    instance_info = VMM.get_instance_info(instance_id)
    mig_drv = migration_drivers.get_migration_driver(instance_info.backend)
    return mig_drv.cancel_migrate_instance(instance_id)


def resume_migrate_instance(instance_id, mig_params):
    """
    Resumes a paused instance migration.

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param mig_params: A dictionary of migration parameters.
    :type mig_params: dict
    """
    instance_info = VMM.get_instance_info(instance_id)
    mig_drv = migration_drivers.get_migration_driver(instance_info.backend)
    mig_drv.resume_migrate_instance(instance_id, mig_params)
