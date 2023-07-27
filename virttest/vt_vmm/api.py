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
# Copyright: Red Hat Inc. 2024
# Authors: Yongxue Hong <yhong@redhat.com>

import logging
import threading
import os
import pickle

from virttest.vt_cluster import cluster

from virttest import utils_misc
from virttest import data_dir

from .instance_api import InstanceAPI
from .task_api import MigrationTaskAPI

from .objects.instance import Instance
from .objects.instance_spec_libvirt import LibvirtSpec
from .objects.instance_spec_qemu import QemuSpec
from .objects.migration_task import LiveMigrationTask
from .objects.migration_state import MigrationState

LOG = logging.getLogger("avocado." + __name__)

VT_MIGRATION_TIMEOUT = 3600


class VMMError(Exception):
    pass


class _VirtualMachinesManager(object):
    """
    Manages the running instances from creation to destruction.
    """

    def __init__(self):
        self._filename = os.path.join(data_dir.get_base_backend_dir(),
                                      "vmm_instances")

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
        return self._instances.get(instance_id)

    def get_instance_node(self, instance_id):
        instance = self._get_instance(instance_id)
        return instance.node

    def _get_migration_task(self, instance_id):
        return self._instance_migration_tasks.get(instance_id)

    def _get_all_migration_task(self):
        return self._instance_migration_tasks.values()

    def define_instance(self, node, config):
        """
        Define an instance by the configuration.
        Note: This method just define the information, not start it.
              The config is passed by calling instance.define_instance_config
        """

        instance_id = config["metadata"]["id"]
        name = config["metadata"]["name"]
        kind = config["kind"]
        spec = config["spec"]
        if instance_id in self._instances:
            raise VMMError(f"The instance {name}({instance_id}) was defined")

        LOG.info(f"Define an instance {instance_id} of {name} on {node}")
        instance = Instance(instance_id, name, kind, spec)
        instance.node = cluster.get_node_by_tag(node)
        self._instances[instance_id] = instance
        self._instance_api.build_instance(instance)
        self._save()
        return instance_id

    def update_instance(self, instance_id, updated_spec):
        """
        Update the instance with the spec.

        :param instance_id: The instance id.
        :type instance_id: str
        :param updated_spec: The instance spec to be updated
        :type updated_spec: vt_vmm.spec.Spec
        """
        LOG.info(
            f"Update the instance {instance_id} with {updated_spec}")
        instance = self._get_instance(instance_id)
        instance.update(updated_spec)

    def start_instance(self, instance_id):
        """
        Start an instance.

        :param instance_id: The instance id.
        :type instance_id: str
        """
        LOG.info(f"Start the instance {instance_id}")
        instance = self._get_instance(instance_id)
        self._instance_api.run_instance(instance)

    def stop_instance(self, instance_id, graceful=True,
                      timeout=120, shutdown_cmd=None, username=None,
                      password=None, prompt=None):
        """
        Stop the instance.

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
        self._instance_api.stop_instance(instance, graceful, timeout,
                                         shutdown_cmd, username, password, prompt)

    def create_instance(self, node, config):
        """
        Create an instance.
        """
        instance_id = self.define_instance(node, config)
        try:
            self.start_instance(instance_id)
        except Exception as e:
            self.stop_instance(instance_id)
            self.undefine_instance(instance_id)
            raise e

    def destroy_instance(self, instance_id, graceful=True,
                         timeout=120, free_mac_addresses=True):
        try:
            self.stop_instance(instance_id, graceful, timeout)
        finally:
            self.undefine_instance(instance_id, free_mac_addresses)

    def pause_instance(self, instance_id):
        """
        Pause the instance

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
        """
        LOG.info(f"Undefine the instance {instance_id}")
        instance = self._get_instance(instance_id)
        # FIXME: can not get the instance as it is None when doing env_process.preprocess
        if instance is None:
            return
        self._instance_api.undefine_instance(instance, free_mac_addresses)
        del self._instances[instance_id]
        self._save()

    def get_instance_consoles(self, console_type, instance_id):
        """
        Get the console information of the instance

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

    def get_instance_devices(self, instance_id):
        instance = self._get_instance(instance_id)
        devices = []
        return devices

    def get_instance_process_info(self, instance_id, name):
        """
        Get the process information of the instance.

        :param instance_id: the instance ID
        :type instance_id: str
        :return: The process information contains the status, output and pid.
        :rtype: dict
        """
        instance = self._get_instance(instance_id)
        if not instance:
            return {}

        instance_type = instance.kind
        if instance_type == "qemu":
            return self._instance_api.get_process_info(instance, name)
        raise VMMError(f"Not support the instance type {instance_type}")

    def get_instance_pid(self, instance_id):
        instance = self._get_instance(instance_id)

        instance_type = instance.kind
        if instance_type == "qemu":
            return self._instance_api.get_pid(instance)
        raise VMMError(f"Not support the instance type {instance_type}")

    def register_migration_task(self, instance_id, mig_task):
        """
        Register a migration task

        :param instance_id:
        :param mig_task:
        :return:
        :return:
        """
        if not isinstance(mig_task, LiveMigrationTask):
            raise ValueError
        self._instance_migration_tasks[instance_id] = mig_task

    def build_migration_task(self, instance_id, dest_node, migration_config):
        """
        Build a migration task

        :param instance_id:
        :param dest_node: The id of the destination node
        :param migration_config:
        :return:
        """
        instance = self._get_instance(instance_id)
        mig_task = self._mig_task_api.build_task(instance, dest_node, migration_config)
        mig_task.status = MigrationState.ACCEPTED
        self.register_migration_task(instance_id, mig_task)

    def do_migration_task(
        self, mig_task, async_mig=False, timeout=VT_MIGRATION_TIMEOUT
    ):
        if mig_task in self._get_all_migration_task():
            if not async_mig:
                self._mig_task_api.execute_task(mig_task, timeout)
            else:
                thread_task = threading.Thread(
                    target=self._mig_task_api.execute_task,
                    args=(
                        mig_task,
                        timeout,
                    ),
                )
                thread_task.daemon = True
                thread_task.start()
                thread_task.join(timeout)
        else:
            raise ValueError

    def migrate_instance(
        self,
        instance_id,
        dest_node,
        migration_config,
        async_mig=False,
        timeout=VT_MIGRATION_TIMEOUT,
    ):
        """
        Migrate the instance to another host

        :param instance_id: the id instance
        :type instance_id: str
        :param dest_node: the destination node
        :type dest_node: node.Node
        :param migration_config: the configration of the migration
                                 The schema of the migration configuration:
                                 {
                                    "flags": (), # e.g: (LIVE, OFFLINE, AUTO_CONVERGE, POSTCOPY, COMPRESSED, etc)
                                    "params": {} # The parameters of the migration depends on the driver
                                 }

        :type migration_config: dict
        :param timeout: timeout for migration task
        :type timeout: float
        :return: True if migrate successful otherwise False
        """
        instance = self._get_instance(instance_id)
        LOG.info(
            f"Going to try to migrate the instance {instance.name} "
            f"to node {dest_node.name} with the configuration: {migration_config}"
        )
        self.build_migration_task(instance_id, dest_node, migration_config)
        mig_task = self._get_migration_task(instance_id)
        self.do_migration_task(mig_task, async_mig, timeout)

    def cancel_migrate_instance(self, instance_id):
        """
        Cancel the migrating task.

        :param instance_id:
        :return:
        """
        mig_task = self._get_migration_task(instance_id)
        self._mig_task_api.cancel_task(mig_task)

    def resume_migrate_instance(self, instance_id):
        """
        Recover the paused migration task.

        :param instance_id:
        :return:
        """
        mig_task = self._get_migration_task(instance_id)
        self._mig_task_api.resume_task(mig_task)

    def get_migrate_instance_info(self, instance_id):
        mig_task = self._get_migration_task(instance_id)
        return mig_task.get_migrate_info()


def _build_spec(name, kind, vm_params, node):
    # request the resource for vm before generate the spec
    specs = {
        "qemu": QemuSpec,
        "libvirt": LibvirtSpec,
    }

    if kind not in specs:
        raise OSError("No supports the %s spec" % kind)
    return specs.get(kind)(name, vm_params, node)


def define_instance_config(name, vm_params, node):
    """
    This interface is to handle the resource allocation and define the config
    The resource allocation should be done before generating the spec.
    # TODO: Rename the interface later.

    :param name: The VM name
    :type name: str
    :param vm_params: The parameters of the VM
    :type vm_params: virttest.utils_params.Params
    :return: The configration of the instance.
    :rtype: dict
    """
    metadata = dict()
    metadata["name"] = name
    # Unique VT ID of the whole cluster
    metadata["id"] = utils_misc.generate_random_string(16)
    kind = vm_params.get("vm_type")
    # request the resource before generate the spec
    spec = _build_spec(name, kind, vm_params, node)
    # suggestion: return a spec instance(class) by build spec:
    # decouple spec and json.
    config = {"kind": kind, "metadata": metadata, "spec": spec.to_json()}
    return config


vmm = _VirtualMachinesManager()
