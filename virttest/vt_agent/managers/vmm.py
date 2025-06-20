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
import os
import pickle

from drivers.instance.libvirt import LibvirtInstanceDriver
from drivers.instance.qemu import QemuInstanceDriver
from virttest import virt_vm

LOG = logging.getLogger("avocado.service." + __name__)


class VMMigrateProtoUnsupportedError(virt_vm.VMMigrateProtoUnknownError):

    """
    When QEMU tells us it doesn't know about a given migration protocol.

    This usually happens when we're testing older QEMU. It makes sense to
    skip the test in this situation.
    """

    def __init__(self, protocol=None, output=None):
        """
        Initializes the VMMigrateProtoUnsupportedError.

        :param protocol: The migration protocol that is not supported.
        :param output: The output from QEMU.
        """
        self.protocol = protocol
        self.output = output

    def __str__(self):
        """
        Returns a string representation of the error.
        """
        return (
            "QEMU reports it doesn't know migration protocol '%s'. "
            "QEMU output: %s" % (self.protocol, self.output)
        )


def get_instance_driver(instance_id, kind):
    """
    Gets a specific instance driver.

    :param instance_id: The ID of the instance.
    :param kind: The type of driver to get ('qemu' or 'libvirt').
    :return: An instance of the requested driver.
    :raises OSError: If the requested driver is not supported.
    """
    _drivers = {
        "qemu": QemuInstanceDriver,
        "libvirt": LibvirtInstanceDriver,
    }

    if kind not in _drivers:
        raise OSError("Unsupported the %s instance driver" % kind)
    return _drivers.get(kind)(instance_id)


class VMMError(Exception):
    """
    A VMM-related error.
    """
    pass


class VirtualMachinesManager(object):
    """
    Manage the instance resource in local.

    """
    def __init__(self):
        """
        Initializes the VirtualMachinesManager.
        """
        self._filename = "/var/instances"

    @property
    def instances(self):
        """
        Gets the instances from the file.

        :return: A dictionary of instances.
        """
        return self._load()

    def _dump_instances(self, instances):
        """
        Dumps the instances to a file.

        :param instances: A dictionary of instances.
        """
        with open(self._filename, "wb") as details:
            pickle.dump(instances, details)

    def _load_instances(self):
        """
        Loads the instances from the file.

        :return: A dictionary of instances.
        """
        if os.path.exists(self._filename):
            with open(self._filename, "rb") as instances:
                return pickle.load(instances)
        return {}

    def _save(self, instances):
        """
        Saves the instances to the file.

        :param instances: A dictionary of instances.
        """
        self._dump_instances(instances)

    def _load(self):
        """
        Loads the instances from the file.

        :return: A dictionary of instances.
        """
        return self._load_instances()

    def register_instance(self, instance_id, info):
        """
        Registers an instance.

        :param instance_id: The ID of the instance to register.
        :param info: A dictionary of instance information.
        :return: True if the instance was registered successfully,
                 False otherwise.
        """
        if instance_id in self.instances:
            LOG.error("The instance %s is already registered.", instance_id)
            return False
        instances = self._load()
        instances[instance_id] = info
        self._save(instances)
        return True

    def unregister_instance(self, instance_id):
        """
        Unregisters an instance.

        :param instance_id: The ID of the instance to unregister.
        :return: True if the instance was unregistered successfully,
                 False otherwise.
        """
        instances = self._load()
        if instance_id in instances.copy():
            del instances[instance_id]
            self._save(instances)
            return True
        LOG.error("The instance %s is not registered" % instance_id)
        return False

    def get_instance(self, instance_id):
        """
        Gets an instance.

        :param instance_id: The ID of the instance to get.
        :return: A dictionary of instance information, or None if the
                 instance is not found.
        """
        return self.instances.get(instance_id)

    def update_instance(self, instance_id, info):
        """
        Updates an instance.

        :param instance_id: The ID of the instance to update.
        :param info: A dictionary of instance information to update.
        """
        instances = self._load()
        instances.get(instance_id).update(info)
        self._save(instances)

    @staticmethod
    def build_instance(instance_id, driver_kind, spec, migrate_incoming=None):
        """
        Builds an instance.

        :param instance_id: The ID of the instance to build.
        :param driver_kind: The kind of driver to use ('qemu' or 'libvirt').
        :param spec: The specification for the instance.
        :param migrate_incoming: The migration information for the instance.
        :return: A dictionary of instance information.
        """
        # TODO: The TODO comment about defining instance_info should be addressed.
        #  A more robust solution would be to create a dedicated InstanceInfo class
        #  or a TypedDict (for Python 3.8+) to define a clear structure.
        #  This would improve code completion, static analysis, and readability
        #  by making the shape of the instance_info object explicit.
        instance_info = dict()
        instance_info["driver_kind"] = driver_kind
        instance_driver = get_instance_driver(instance_id, driver_kind)
        instance_info["driver"] = instance_driver
        instance_driver.create_devices(spec)
        instance_info["devices"] = instance_driver.get_devices()
        instance_info["caps"] = instance_driver.probe_capabilities()
        instance_info["mig_params"] = instance_driver.probe_migration_parameters()

        if migrate_incoming:
            instance_info["migrate_incoming"] = migrate_incoming
        return instance_info

    def run_instance(self, instance_id):
        """
        Runs an instance.

        :param instance_id: The ID of the instance to run.
        """
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        migrate_incoming = instance_info.get("migrate_incoming")
        migrate_inc_uri = migrate_incoming.get("uri") if migrate_incoming else None

        instance_driver.make_cmdline(migrate_inc_uri)
        cmdline = instance_driver.get_cmdline()
        instance_info["cmdline"] = cmdline
        instance_driver.start(cmdline)
        self.update_instance(
            instance_id, {"driver": instance_driver, "cmdline": cmdline}
        )

    def attach_instance_device(self, instance_id, device_spec, monitor_id=None):
        """
        Attaches a device to an instance.

        :param instance_id: The ID of the instance to attach the device to.
        :param device_spec: The specification of the device to attach.
        :param monitor_id: The ID of the monitor to use.
        :return: The result of the device attachment.
        """
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        return instance_driver.attach_device(device_spec, monitor_id)

    def detach_instance_device(self, instance_id, dev_spec, monitor_id=None):
        """
        Detaches a device from an instance.

        :param instance_id: The ID of the instance to detach the device from.
        :param dev_spec: The specification of the device to detach.
        :param monitor_id: The ID of the monitor to use.
        :return: The result of the device detachment.
        """
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        return instance_driver.detach_device(dev_spec, monitor_id)

    def get_instance_pid(self, instance_id):
        """
        Return the VM's PID.  If the VM is dead return None.

        :note: This works under the assumption that self.process.get_pid()
        :return: the PID of the parent shell process.
        """
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        return instance_driver.get_pid()

    def is_instance_dead(self, instance_id):
        """
        Return True if the qemu process is dead.

        :param instance_id: The ID of the instance to check.
        :return: True if the instance is dead, False otherwise.
        """
        instance_info = self.get_instance(instance_id)
        _process = instance_info.get("process")
        instance_driver = instance_info["driver"]
        return not _process or not instance_driver.is_proc_alive()

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
        Stops an instance.

        :param instance_id: The ID of the instance to stop.
        :param graceful: Whether to stop the instance gracefully.
        :param timeout: The timeout for stopping the instance.
        :param shutdown_cmd: The command to use to shut down the instance.
        :param username: The username to use to shut down the instance.
        :param password: The password to use to shut down the instance.
        :param prompt: The prompt to expect when shutting down the instance.
        """
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        instance_driver.stop(
            graceful, timeout, shutdown_cmd, username, password, prompt
        )

    def pause_instance(self, instance_id):
        """
        Pauses an instance.

        :param instance_id: The ID of the instance to pause.
        :return: The result of pausing the instance.
        """
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        return instance_driver.pause()

    def is_instance_paused(self, instance_id):
        """
        Checks if an instance is paused.

        :param instance_id: The ID of the instance to check.
        :return: True if the instance is paused, False otherwise.
        """
        instance_info = self.get_instance(instance_id)
        _process = instance_info.get("process")
        instance_driver = instance_info["driver"]
        return (
            _process and instance_driver.is_proc_alive() and instance_driver.is_paused()
        )

    def continue_instance(self, instance_id):
        """
        Continues a paused instance.

        :param instance_id: The ID of the instance to continue.
        :return: The result of continuing the instance.
        """
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        return instance_driver.cont()

    def is_instance_running(self, instance_id):
        """
        Checks if an instance is running.

        :param instance_id: The ID of the instance to check.
        :return: True if the instance is running, False otherwise.
        """
        instance_info = self.get_instance(instance_id)
        _process = instance_info.get("process")
        instance_driver = instance_info["driver"]
        return _process and instance_driver.is_proc_alive()

    def get_instance_consoles(self, instance_id, console_type):
        """
        Gets the consoles for an instance.

        :param instance_id: The ID of the instance.
        :param console_type: The type of console to get.
        :return: The consoles for the instance.
        """
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        if console_type == "serial":
            return instance_driver.get_serial_consoles()
        elif console_type == "vnc":
            return instance_driver.get_vnc_consoles()
        elif console_type == "spice":
            return instance_driver.get_spice_consoles()
        else:
            raise NotImplementedError

    def get_instance_serials(self, instance_id):
        """
        Gets the serials for an instance.

        :param instance_id: The ID of the instance to get the serials for.
        """
        return

    def get_instance_process_info(self, instance_id, name):
        """
        Gets information about a process running on an instance.

        :param instance_id: The ID of the instance.
        :param name: The name of the process to get information about.
        :return: Information about the process.
        """
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        return instance_driver.get_proc_info(name)

    def cleanup_instance(self, instance_id, free_mac_addresses=True):
        """
        Cleans up an instance.

        :param instance_id: The ID of the instance to clean up.
        :param free_mac_addresses: Whether to free the MAC addresses of the
                                   instance.
        """
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        instance_driver.cleanup(free_mac_addresses)

    def set_instance_migration_parameter(
        self, instance_id, connect_id, parameter, value
    ):
        """
        Sets a migration parameter for an instance.

        :param instance_id: The ID of the instance.
        :param connect_id: The ID of the connection to set the parameter on.
        :param parameter: The parameter to set.
        :param value: The value to set the parameter to.
        :return: The result of setting the parameter.
        """
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        return instance_driver.set_migration_parameter(connect_id, parameter, value)

    def check_instance_capability(self, instance_id, capability):
        """
        Checks if an instance has a capability.

        :param instance_id: The ID of the instance to check.
        :param capability: The capability to check for.
        :return: True if the instance has the capability, False otherwise.
        """
        instance_info = self.get_instance(instance_id)
        return capability in instance_info.get("caps", [])

    def check_instance_migration_parameter(self, instance_id, parameter):
        """
        Checks if an instance has a migration parameter.

        :param instance_id: The ID of the instance to check.
        :param parameter: The migration parameter to check for.
        :return: True if the instance has the migration parameter,
                 False otherwise.
        """
        instance_info = self.get_instance(instance_id)
        return parameter in instance_info.get("mig_params", [])
