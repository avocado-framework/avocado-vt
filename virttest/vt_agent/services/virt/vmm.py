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


import logging
import re

from drivers import migration as migration_drivers
from managers import vmm

VMM = vmm.VirtualMachinesManager()

LOG = logging.getLogger("avocado.service." + __name__)


def build_instance(instance_id, instance_driver, instance_spec, migrate_inc_uri=None):
    """
    Builds and registers a new virtual machine instance.

    :param instance_id: A unique identifier for the instance.
    :type instance_id: str
    :param instance_driver: The driver to be used for the instance (e.g., 'qemu').
    :type instance_driver: str
    :param instance_spec: A dictionary containing the instance's configuration.
    :type instance_spec: dict
    :param migrate_inc_uri: The URI for incoming migration. Defaults to None.
    :type migrate_inc_uri: str, optional
    :raises vmm.VMMError: If an instance with the given ID is already registered.
    """
    if instance_id in VMM.instances:
        raise vmm.VMMError(f"The instance {instance_id} was registered.")

    LOG.info(f"Build the instance '{instance_id}'")
    instance_info = VMM.build_instance(
        instance_id, instance_driver, instance_spec, migrate_inc_uri
    )
    VMM.register_instance(instance_id, instance_info)


def run_instance(instance_id):
    """
    Starts a pre-built virtual machine instance.

    :param instance_id: The unique identifier of the instance to run.
    :type instance_id: str
    """
    LOG.info(f"Run the instance '{instance_id}'")
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
    :param graceful: Whether to attempt a graceful shutdown. Defaults to True.
    :type graceful: bool, optional
    :param timeout: The timeout in seconds for the stop operation. Defaults to 120.
    :type timeout: int, optional
    :param shutdown_cmd: The command to use for a graceful shutdown. Defaults to None.
    :type shutdown_cmd: str, optional
    :param username: The username for authentication during graceful shutdown. Defaults to None.
    :type username: str, optional
    :param password: The password for authentication during graceful shutdown. Defaults to None.
    :type password: str, optional
    :param prompt: A regex pattern for the expected shell prompt. Defaults to None.
    :type prompt: str, optional
    """
    LOG.info(f"Stop the instance '{instance_id}'")
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
    LOG.info(f"Pause the instance '{instance_id}'")
    VMM.pause_instance(instance_id)


def continue_instance(instance_id):
    """
    Resumes (continues) a paused virtual machine instance.

    :param instance_id: The unique identifier of the instance to continue.
    :type instance_id: str
    """
    LOG.info(f"Continue the instance '{instance_id}'")
    VMM.continue_instance(instance_id)


def get_instance_consoles(instance_id, console_type):
    """
    Retrieves console information for a specific instance.

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param console_type: The type of console to retrieve (e.g., 'monitor', 'serial').
    :type console_type: str
    :return: The console information, format depends on the manager implementation.
    :rtype: any
    """
    return VMM.get_instance_consoles(instance_id, console_type)


def get_instance_process(instance_id, name):
    """
    Gets information about a process related to the instance.

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param name: The name of the process to look for (e.g., 'qemu').
    :type name: str
    :return: A dictionary containing process information if found, otherwise None.
    :rtype: dict or None
    """
    if VMM.get_instance(instance_id):
        return VMM.get_instance_process_info(instance_id, name)
    return None


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
    LOG.info(f"Clean up the instance '{instance_id}'")
    VMM.cleanup_instance(instance_id, free_mac_addresses)
    VMM.unregister_instance(instance_id)


def get_instance_pid(instance_id):
    """
    Gets the process ID (PID) of the main instance process.

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :return: The process ID of the instance, or None if not found.
    :rtype: int or None
    """
    return VMM.get_instance_pid(instance_id)


def attach_instance_device(instance_id, device_spec, monitor_id=None):
    """
    Attaches a device to a running instance (hotplug).

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param device_spec: A dictionary describing the device to attach.
    :type device_spec: dict
    :param monitor_id: The ID of the monitor to use for the operation. Defaults to None.
    :type monitor_id: str, optional
    :return: The result of the device attachment operation.
    :rtype: any
    """
    return VMM.attach_instance_device(instance_id, device_spec, monitor_id)


def detach_instance_device(instance_id, dev_spec, monitor_id=None):
    """
    Detaches a device from a running instance (hot-unplug).

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param dev_spec: A dictionary describing the device to detach.
    :type dev_spec: dict
    :param monitor_id: The ID of the monitor to use for the operation. Defaults to None.
    :type monitor_id: str, optional
    :return: The result of the device detachment operation.
    :rtype: any
    """
    return VMM.detach_instance_device(instance_id, dev_spec, monitor_id)


def check_instance_capability(instance_id, cap_name):
    """
    Checks if the instance hypervisor supports a given capability.

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param cap_name: The name of the capability to check.
    :type cap_name: str
    :return: True if the capability is supported, False otherwise.
    :rtype: bool
    """
    LOG.info(f"Check the capability {cap_name} of the instance '{instance_id}'")
    return VMM.check_instance_capability(instance_id, cap_name)


def check_instance_migration_parameter(instance_id, param_name):
    """
    Checks a specific migration parameter for the instance.

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param param_name: The name of the migration parameter to check.
    :type param_name: str
    :return: The value or status of the migration parameter.
    :rtype: any
    """
    LOG.info(
        f"Check the migration parameter {param_name} of the instance '{instance_id}'"
    )
    return VMM.check_instance_migration_parameter(instance_id, param_name)


def migrate_instance_prepare(instance_id, driver_kind, spec, mig_params):
    """
    Prepares the system for an instance migration.

    :param instance_id: The unique identifier of the instance to migrate.
    :type instance_id: str
    :param driver_kind: The kind of migration driver to use.
    :type driver_kind: str
    :param spec: The specification for the migration.
    :type spec: dict
    :param mig_params: A dictionary of migration parameters.
    :type mig_params: dict
    :return: The result of the migration preparation.
    :rtype: any
    """
    LOG.info(f"Prepare the migration of the instance({instance_id})")
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_prepare(instance_id, driver_kind, spec, mig_params)


def migrate_instance_perform(instance_id, mig_params):
    """
    Performs the migration of an instance from the source host.

    :param instance_id: The unique identifier of the instance to migrate.
    :type instance_id: str
    :param mig_params: A dictionary of migration parameters.
    :type mig_params: dict
    :return: The result of the migration operation.
    :rtype: any
    """
    LOG.info(f"Perform the migration of the instance({instance_id})")
    instance_info = VMM.get_instance(instance_id)
    driver_kind = instance_info["driver_kind"]
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_perform(instance_id, mig_params)


def migrate_instance_query(instance_id):
    """
    Queries the status of an ongoing migration.

    :param instance_id: The unique identifier of the migrating instance.
    :type instance_id: str
    :return: A tuple containing migration status and details. Returns (None, "{}")
             if the instance is not found.
    :rtype: tuple
    """
    instance_info = VMM.get_instance(instance_id)
    if instance_info:
        driver_kind = instance_info["driver_kind"]
        mig_drv = migration_drivers.get_migration_driver(driver_kind)
        return mig_drv.migrate_instance_query(instance_id)
    else:
        return None, "{}"


def migrate_instance_finish(instance_id, mig_ret, mig_params):
    """
    Finishes the migration process on the destination host.

    :param instance_id: The unique identifier of the migrated instance.
    :type instance_id: str
    :param mig_ret: The return value from the migration perform step.
    :type mig_ret: any
    :param mig_params: A dictionary of migration parameters.
    :type mig_params: dict
    :return: The result of the finalization step.
    :rtype: any
    """
    LOG.info(f"Finish the migration of the instance({instance_id})")
    instance_info = VMM.get_instance(instance_id)
    driver_kind = instance_info["driver_kind"]
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_finish(instance_id, mig_ret, mig_params)


def migrate_instance_confirm(instance_id, inmig_ret, mig_params):
    """
    Confirms a completed migration on the source host.

    :param instance_id: The unique identifier of the migrated instance.
    :type instance_id: str
    :param inmig_ret: The return value from the incoming migration process.
    :type inmig_ret: any
    :param mig_params: A dictionary of migration parameters.
    :type mig_params: dict
    :return: The result of the confirmation step.
    :rtype: any
    """
    LOG.info(f"Confirm the migration of the instance({instance_id})")
    instance_info = VMM.get_instance(instance_id)
    driver_kind = instance_info["driver_kind"]
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_confirm(instance_id, inmig_ret, mig_params)


def migrate_instance_cancel(instance_id):
    """
    Cancels an ongoing instance migration.

    :param instance_id: The unique identifier of the instance whose migration should be canceled.
    :type instance_id: str
    :return: The result of the cancellation operation.
    :rtype: any
    """
    instance_info = VMM.get_instance(instance_id)
    driver_kind = instance_info["driver_kind"]
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_cancel(instance_id)


def migrate_instance_resume(instance_id, mig_params):
    """
    Resumes a paused instance migration.

    :param instance_id: The unique identifier of the instance.
    :type instance_id: str
    :param mig_params: A dictionary of migration parameters.
    :type mig_params: dict
    :return: The result of the resume operation.
    :rtype: any
    """
    instance_info = VMM.get_instance(instance_id)
    driver_kind = instance_info["driver_kind"]
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_resume(instance_id, mig_params)
