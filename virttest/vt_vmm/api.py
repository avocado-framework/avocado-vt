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
import threading

from virttest import data_dir, utils_misc
from virttest.vt_cluster import cluster
from virttest.vt_vmm.instance_api import InstanceAPI
from virttest.vt_vmm.objects.instance import InstanceLibvirt, InstanceQemu
from virttest.vt_vmm.objects.tasks.migration_task import LiveMigrationTask
from virttest.vt_vmm.task_api import MigrationTaskAPI
from virttest.vt_vmm.utils.instance_spec import libvirt_spec, qemu_spec

LOG = logging.getLogger("avocado." + __name__)

VT_MIGRATION_TIMEOUT = 3600


class VMMError(Exception):
    pass


class VMMInstanceError(VMMError):
    pass


class VMMMigrationTaskError(VMMError):
    pass


class _VirtualMachinesManager(object):
    """
    Manages the running instances from creation to destruction, and provides
    the essential interfaces for the users.
    """

    def __init__(self):
        self._filename = os.path.join(data_dir.get_base_backend_dir(), "vmm_instances")

        if os.path.isfile(self._filename):
            self._instances = self._load()
        else:
            self._instances = {}

        self._instance_api = InstanceAPI()
        self._mig_task_api = MigrationTaskAPI()
        self._instance_migration_tasks = {}

    def cleanup_instances(self):
        self._instances = {}
        if os.path.isfile(self._filename):
            os.unlink(self._filename)

    def _save(self):
        with open(self._filename, "wb") as f:
            pickle.dump(self._instances, f, protocol=0)

    def _load(self):
        with open(self._filename, "rb") as f:
            return pickle.load(f)

    def _get_instance(self, instance_id):
        instance = self._instances.get(instance_id)
        if not instance:
            raise VMMInstanceError(
                f'No found instance "{instance_id}" in {self._instances}'
            )
        return instance

    def get_instance_node(self, instance_id):
        """
        Get the VM instance node by the instance id.

        :param instance_id: The instance ID
        :type instance_id: str
        :return: The instance object
        :rtype: vt_cluster.node.Node
        """
        instance = self._get_instance(instance_id)
        return instance.node

    def _get_migration_task(self, instance_id):
        return self._instance_migration_tasks.get(instance_id)

    def _get_all_migration_task(self):
        return self._instance_migration_tasks.values()

    def define_instance(self, node, config):
        """
        Define an instance by the configuration on the node.
        The instance definition will be registered.
        Note: This just define the instance object, will not start it.
              The config is created by the instance.define_instance_config

        :param node: The related node tag
        :type node: str
        :param config: The configuration of the instance
        :type config: dict
        """
        instance_id = config["metadata"]["id"]
        name = config["metadata"]["name"]
        kind = config["kind"]
        specs = config["specs"]
        if instance_id in self._instances:
            raise VMMError(f"The instance {name}({instance_id}) was defined")

        LOG.info(f"Define an instance {instance_id} of {name} on {node}")
        if kind == "qemu":
            instance = InstanceQemu(instance_id, name, specs)
        elif kind == "libvirt":
            instance = InstanceLibvirt(instance_id, name, specs)
        else:
            raise VMMError(f"Unsupported kind {kind}")

        instance.node = cluster.get_node_by_tag(node)
        self._instances[instance_id] = instance
        self._save()
        self._instance_api.build_instance(instance)
        return instance_id

    def update_instance(self, instance_id, updated_spec):
        """
        Update the instance with the specified spec.
        # TODO:

        :param instance_id: The instance id.
        :type instance_id: str
        :param updated_spec: The instance spec to be updated
        :type updated_spec: vt_vmm.spec.Spec
        """
        LOG.info(f"Update the instance {instance_id} with {updated_spec}")
        instance = self._get_instance(instance_id)
        instance.update(updated_spec)

    def start_instance(self, instance_id):
        """
        Start the instance.

        :param instance_id: The instance id.
        :type instance_id: str
        """
        LOG.info(f"Start the instance {instance_id}")
        instance = self._get_instance(instance_id)
        self._instance_api.run_instance(instance)

    def stop_instance(
        self,
        instance_id,
        graceful=True,
        timeout=120,
        shutdown_cmd=None,
        username=None,
        password=None,
        prompt=None,
    ):
        """
        Stop the instance.
        Notes: It just stops the instance, but the instance definition will not
                be removed.

        :param instance_id: The instance id.
        :type instance_id: str
        :param graceful: Whether to use graceful shutdown.
        :type graceful: bool
        :param timeout: The timeout for graceful shutdown.
        :type timeout: int
        :param shutdown_cmd: The shutdown command.
        :type shutdown_cmd: str
        :param username: The username for SSH.
        :type username: str
        :param password: The password for SSH.
        :type password: str
        :param prompt: The prompt for SSH.
        :type prompt: str
        """
        LOG.info(f"Stop the instance {instance_id}")
        instance = self._get_instance(instance_id)
        self._instance_api.stop_instance(
            instance, graceful, timeout, shutdown_cmd, username, password, prompt
        )

    def create_instance(self, node, config):
        """
        Create the instance.

        :param node: The related node tag
        :type node: str
        :param config: The configuration of the instance
        :type config: dict
        """
        instance_id = self.define_instance(node, config)
        try:
            self.start_instance(instance_id)
        except Exception as e:
            self.stop_instance(instance_id)
            self.undefine_instance(instance_id)
            raise VMMError(f"Failed to create the instance as {str(e)}")

    def destroy_instance(self, instance_id):
        """
        Destroy the instance. It will stop the instance forcibly and
        remove the related definition and resource.

        :param instance_id: The instance ID
        :type instance_id: str
        """
        try:
            self.stop_instance(instance_id, False)
        finally:
            self.undefine_instance(instance_id, True)

    def pause_instance(self, instance_id):
        """
        Pause the instance.

        :param instance_id: The instance id.
        :type instance_id: str
        """
        LOG.info(f"Pause the instance {instance_id}")
        instance = self._get_instance(instance_id)
        self._instance_api.pause_instance(instance)

    def continue_instance(self, instance_id):
        """
        Continue the instance.

        :param instance_id: The instance id.
        :type instance_id: str
        """
        LOG.info(f"Continue the instance {instance_id}")
        instance = self._get_instance(instance_id)
        self._instance_api.continue_instance(instance)

    def undefine_instance(self, instance_id, free_mac_addresses=True):
        """
        Delete the instance from the VMM:
        1. delete the instance info from the VMM resource.
        2. reclaim the related resource on the worker node.

        :param instance_id: The instance id.
        :type instance_id: str
        :param free_mac_addresses: Free the mac address allocated.
        :type free_mac_addresses: bool
        """
        LOG.info(f"Undefine the instance {instance_id}")
        try:
            instance = self._get_instance(instance_id)
        except VMMInstanceError:
            # FIXME: can not get the instance as it is None when doing env_process.preprocess
            return
        self._instance_api.undefine_instance(instance, free_mac_addresses)
        del self._instances[instance_id]
        self._save()

    def get_instance_consoles(self, console_type, instance_id):
        """
        Get the console information of the instance
        # TODO:

        :param console_type: the console type
        :type console_type: str
        :param instance_id: the instance id
        :type instance_id: str
        :return: the console information
        :rtype: list[dict, ]
        """
        LOG.info(f"Getting the information of {console_type} the console")
        instance = self._get_instance(instance_id)
        console_info = []
        if console_type == "monitor":
            consoles = self._instance_api.get_monitor_consoles(instance)
            for console in consoles:
                console_info.append(
                    {
                        "name": console.get("name"),
                        "type": console.get("type"),  # hmp, qmp
                        "protocol": console.get("protocol"),  # tcp, unix
                        "uri": console.get("uri"),
                    }
                )

        elif console_type == "vnc":
            consoles = self._instance_api.get_vnc_consoles(instance)
            for console in consoles:
                console_info.append(
                    {
                        "name": console.get("name"),
                        "password": console.get("password"),
                        "uri": console.get("uri"),
                    }
                )

        elif console_type == "serial":
            consoles = self._instance_api.get_serial_consoles(instance)
            for console in consoles:
                console_info.append(
                    {
                        "name": console.get("name"),
                        "password": console.get("password"),
                        "uri": console.get("uri"),
                    }
                )
        else:
            raise NotImplementedError(f"Not support the console {console_type}")

        return console_info

    def get_instance_spec_info(self, instance_id, condition):
        """
        Get the specification info for the given instance.

        :param instance_id: The instance ID
        :type instance_id: str
        :param condition: The condition for getting
        :return: The instance spec info
        :rtype: dict
        """
        instance = self._get_instance(instance_id)
        return instance.query_spec_info(condition)

    def get_instance_process_info(self, instance_id, name):
        """
        Get the process information of the instance.
        FIXME: It is not good way to expose the process, the process should
                be managed by the VMM. But in order to be compatible with the
                previous interface, we provide such interface for the qemu.

        :param instance_id: the instance ID
        :type instance_id: str
        :return: The process information contains the status, output and pid.
        :rtype: dict
        """
        try:
            instance = self._get_instance(instance_id)
        except VMMInstanceError:
            return {}

        instance_type = instance.kind
        if instance_type == "qemu":
            return self._instance_api.get_process_info(instance, name)
        raise VMMError(f"Not support the instance type {instance_type}")

    def get_instance_pid(self, instance_id):
        """
        Get the instance PID.
        FIXME: To keep the compatibility, we provide this interface for the upper
                user level. Actually, we do not support to expose the pid, but let
                the VMM manage it.

        :param instance_id: The instance ID
        :return: The PID
        """
        instance = self._get_instance(instance_id)
        instance_type = instance.kind
        if instance_type == "qemu":
            return self._instance_api.get_pid(instance)
        raise VMMError(f"Not support the instance type {instance_type}")

    def attach_instance_device(self, instance_id, dev_spec, monitor_id=None):
        """
        Attach a device to the instance.

        :param instance_id: The instance id
        :type instance_id: str
        :param dev_spec: The device spec
        :type dev_spec: QemuSpec
        :param monitor_id: The monitor id
        :type monitor_id: str
        :return: Return empty string and Ture if attach the device successfully,
                 otherwise return the error output and False.
        :rtype: (str, bool)
        """
        LOG.info(
            f"Attaching instance device with spec {dev_spec} for instance {instance_id}"
        )
        instance = self._get_instance(instance_id)
        # Insert the device into the instance
        instance.insert_spec(dev_spec)
        return self._instance_api.attach_instance_device(instance, dev_spec, monitor_id)

    def detach_instance_device(self, instance_id, dev_spec, monitor_id=None):
        """
        Detach a device from the instance.

        :param instance_id: The instance id
        :type instance_id: str
        :param dev_spec: The device spec
        :type dev_spec: QemuSpec
        :param monitor_id: The monitor id
        :type monitor_id: str
        :return: Return empty string and Ture if detach the device successfully,
                 otherwise return the error output and False.
        """
        LOG.info(f"Detaching instance device {dev_spec} for instance {instance_id}")
        instance = self._get_instance(instance_id)
        instance.remove_spec(dev_spec)
        return self._instance_api.detach_instance_device(instance, dev_spec, monitor_id)

    def register_migration_task(self, instance_id, mig_task):
        """
        Register a migration task.

        :param instance_id: The instance ID
        :type instance_id: str
        :param mig_task: The migration task
        :type mig_task: LiveMigrationTask
        """
        if not isinstance(mig_task, LiveMigrationTask):
            raise VMMMigrationTaskError(
                f"Not supported migration task type: {mig_task}"
            )
        self._instance_migration_tasks[instance_id] = mig_task

    def build_migration_task(self, instance_id, dest_node, migration_config):
        """
        Build a migration task.

        :param instance_id: The instance ID
        :param dest_node: The destination node
        :type dest_node: vt_cluster.node.Node
        :param migration_config: The related configration of the migration task
        :type migration_config: dict
        """
        instance = self._get_instance(instance_id)
        mig_task = self._mig_task_api.build_task(instance, dest_node, migration_config)
        self.register_migration_task(instance_id, mig_task)

    def do_migration_task(
        self, mig_task, async_mig=False, timeout=VT_MIGRATION_TIMEOUT
    ):
        """
        Execute the migration task.

        :param mig_task: The specified migration task
        :param async_mig: To execute this migration task asynchronously
        :type async_mig: bool
        :param timeout: The timeout for executing the task
        """
        if mig_task in self._get_all_migration_task():
            if not async_mig:
                self._mig_task_api.execute_task(mig_task, timeout)
            else:
                LOG.debug("Executing the migration task in background")
                thread_task = threading.Thread(
                    target=self._mig_task_api.execute_task,
                    args=(
                        mig_task,
                        timeout,
                    ),
                    daemon=True,
                )
                thread_task.start()
        else:
            raise VMMMigrationTaskError(f"No support for the migration task {mig_task}")

    def migrate_instance(
        self,
        instance_id,
        dest_node,
        migration_config,
        async_mig=False,
        timeout=VT_MIGRATION_TIMEOUT,
    ):
        """
        Migrate the instance to another node

        :param instance_id: the id instance
        :type instance_id: str
        :param dest_node: the destination node
        :type dest_node: virttest.vt_cluster.node.Node
        :param migration_config: the configration of the migration
                                 The schema of the migration configuration:
                                 {
                                    "flags": (), # e.g: (LIVE, OFFLINE, AUTO_CONVERGE, POSTCOPY, COMPRESSED, etc)
                                    "params": {} # The parameters of the migration depends on the driver
                                 }

        :type migration_config: dict
        :param async_mig: To execute this migration task asynchronously
        :type async_mig: bool
        :param timeout: timeout for migration task
        :type timeout: float
        """
        instance = self._get_instance(instance_id)
        LOG.info(
            f"Going to try to migrate the instance {instance.name} "
            f"to node {dest_node.tag} with the configuration: {migration_config}"
        )
        self.build_migration_task(instance_id, dest_node, migration_config)
        mig_task = self._get_migration_task(instance_id)
        self.do_migration_task(mig_task, async_mig, timeout)

    def cancel_migrate_instance(self, instance_id):
        """
        Cancel the migrating task.

        :param instance_id: The instance ID
        :return: Ture if cancel the migration task successfully, otherwise False
        """
        mig_task = self._get_migration_task(instance_id)
        return self._mig_task_api.cancel_task(mig_task)

    def resume_migrate_instance(self, instance_id):
        """
        Resume the paused migration task.

        :param instance_id: The instance ID
        :return: Ture if resume the migration task successfully, otherwise False
        """
        mig_task = self._get_migration_task(instance_id)
        return self._mig_task_api.resume_task(mig_task)

    def get_migrate_instance_info(self, instance_id):
        mig_task = self._get_migration_task(instance_id)
        return mig_task.get_migrate_info()

    def check_instance_capability(self, instance_id, cap_name):
        """
        Check if the capability is supported with the given instance

        :param instance_id: The instance ID
        :param cap_name: The capability to be checked
        :return: Ture if the instance support the specified capability, otherwise False
        """
        LOG.info(f"Check the capability {cap_name} for instance {instance_id}")
        instance = self._get_instance(instance_id)
        return self._instance_api.check_capability_instance(instance, cap_name)

    def check_instance_migration_parameter(self, instance_id, param_name):
        """
        Check if the specified migration parameter is supported with the given instance

        :param instance_id: The instance ID
        :param param_name: The migration parameter to be checked
        :return: Ture if the instance support the specified migration parameter, otherwise False
        """

        LOG.info(
            f"Check the migration parameter {param_name} for instance {instance_id}"
        )
        instance = self._get_instance(instance_id)
        return self._instance_api.check_migration_parameter_instance(
            instance, param_name
        )


def _build_specs(name, kind, vm_params, node):
    specs = {
        "qemu": qemu_spec.define_instance_specs,
        "libvirt": libvirt_spec.define_instance_specs,
    }

    if kind not in specs:
        raise OSError("No supports the %s spec" % kind)
    return specs.get(kind)(name, vm_params, node)


def define_instance_config(name, vm_params, node):
    """
    Define the instance's configration by the VM's parameter.

    :param name: The VM name
    :type name: str
    :param vm_params: The parameters of the VM
    :type vm_params: virttest.utils_params.Params
    :param node: The related node tag
    :type node: str
    :return: The configration of the instance.
    :rtype: dict
    """
    metadata = dict()
    metadata["name"] = name
    metadata["id"] = utils_misc.generate_random_string(16)
    kind = vm_params.get("vm_type")
    specs = _build_specs(name, kind, vm_params, node)
    config = {"kind": kind, "metadata": metadata, "specs": specs}
    return config


vmm = _VirtualMachinesManager()
