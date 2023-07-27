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
# Copyright: Red Hat Inc. 2023
# Authors: Yongxue Hong <yhong@redhat.com>

import logging

LOG = logging.getLogger('avocado.' + __name__)

from .spec import get_spec_helper
from .conductor import Conductor

from virttest import utils_misc


class VMMError(Exception):
    pass


class _VirtualMachinesManager(object):
    """
    The virtual machine manager(VMM) is to manager all the VM instances
    on the cluster.
    """

    def __init__(self):
        self._instances = {}

    def get_instance_status(self, instance_id):
        conductor = self._instances.get(instance_id)["conductor"]
        status = conductor.get_instance_status()
        return status

    def define_instance(self, node, config):
        """
        Define an instance by the configuration.
        Note: this method just define the information, not start it
        """
        # info is passed by calling instance.define_instance_info
        instance_id = config["id"]
        if instance_id in self._instances:
            name = config["metadata"]["name"]
            raise VMMError(f"The instance {name}({instance_id}) was defined")

        conductor = Conductor(node, instance_id, config)
        conductor.build_instance()
        self._instances[instance_id] = {"conductor": conductor, "config": config}
        return instance_id

    def get_instance_spec(self, instance_id):
        return self._instances[instance_id]["spec"].copy()

    def update_instance(self, instance_id, spec):
        """
        Update the instance.

        :param instance_id:
        :param spec: The spec instance
        :type spec: Spec object
        :return:
        """
        pass

    def start_instance(self, instance_id):
        """
        Start an instance.
        """
        conductor = self._instances.get(instance_id)["conductor"]
        conductor.run_instance()

    def create_instance(self, node, config):
        """
        Create an instance.
        """
        self.start_instance(self.define_instance(node, config))

    def delete_instance(self, instance_id):
        """
        Delete the instance from the VMM

        """
        try:
            if self.get_instance_status(instance_id) == "running":
                self.stop_instance(instance_id)
        except:
            conductor = self._instances.get(instance_id)["conductor"]
            conductor.kill_instance()

        del self._instances[instance_id]

    def pause_instance(self, instance_id):
        if self.get_instance_status(instance_id) != "paused":
            raise VMMError("Failed to pause")

    def resume_instance(self, instance_id):
        if self.get_instance_status(instance_id) != "running":
            raise VMMError("Failed to resume")

    def reboot_instance(self, instance_id):
        pass

    def get_consoles(self, instance_id):
        consoles = []
        console_info = {}
        console_info["type"] = ""
        console_info["uri"] = ""

        return consoles

    def get_device_metadata(self, instance_id):
        return []

    def get_access_ipv4(self, instance_id):
        return ""

    def get_access_ipv6(self, instance_id):
        return ""

    def list_instances(self):
        instances = []

        for instance_id, info in self._instances.items():
            instance_info = dict()
            instance_info["id"] = instance_id
            instance_info["name"] = info.get("config")["name"]
            instance_info["type"] = info.get("config")["kind"]
            instance_info["status"] = self.get_instance_status(instance_id)
            instance_info["consoles"] = self.get_consoles(instance_id)
            instance_info["access_ipv4"] = self.get_access_ipv4(instance_id)
            instance_info["access_ipv6"] = self.get_access_ipv6(instance_id)
            instance_info["device_metadata"] = self.get_device_metadata(instance_id)
            instances.append(instance_info)

        return instances

    def stop_instance(self, instance_id):
        conductor = self._instances.get(instance_id)["conductor"]
        conductor.stop_instance()

    def get_instance_pid(self, instance_id):
        conductor = self._instances.get(instance_id)["conductor"]
        return conductor.get_instance_pid()


def define_instance_config(name, vm_params):
    """
    This interface is to handle the resource allocation and define the config
    The resource allocation should be done before generating the spec.
    # TODO: rename the interface.

    :param name:
    :param vm_params:
    :return:
    """
    metadata = dict()
    metadata["name"] = name
    # Unique VT ID of the whole cluster
    metadata["id"] = utils_misc.generate_random_string(16)
    kind = vm_params.get("vm_type")
    # add the resource allocation.
    spec_helper = get_spec_helper(kind)
    # suggestion: return a spec instance(class) by build spec:
    # decouple spec and json.
    spec = spec_helper.to_json(vm_params)
    config = {"kind": kind, "metadata": metadata, "spec": spec}
    LOG.debug(f"The config of the instance {name}: {config}")
    return config


vmm = _VirtualMachinesManager()
