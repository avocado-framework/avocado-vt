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


from threading import RLock

from virttest.vt_vmm.objects.states.instance_state import States
from virttest.vt_vmm.objects.exceptions.instance_exception import InstanceStateMisMatchError


class InstanceAPI(object):
    """
    This instance api provides the related instance drivers for the higher level.

    """

    def __init__(self):
        self._lock = RLock()

    @staticmethod
    def _get_client_server(instance):
        return instance.node.proxy.virt.vmm

    def build_instance(self, instance):
        with self._lock:
            if not instance.state:
                client_server = self._get_client_server(instance)
                instance_spec = instance.format_specs(format_type="json")
                client_server.build_instance(
                    instance.uuid, instance.kind, instance_spec
                )
                instance.state = States.DEFINED
            else:
                raise InstanceStateMisMatchError(instance.state, None)

    def run_instance(self, instance):
        with self._lock:
            if instance.state == States.DEFINED:
                client_server = self._get_client_server(instance)
                client_server.run_instance(instance.uuid)
                instance.state = States.RUNNING
            else:
                raise InstanceStateMisMatchError(instance.state, States.DEFINED)

    def stop_instance(
        self,
        instance,
        graceful=True,
        timeout=120,
        shutdown_cmd=None,
        username=None,
        password=None,
        prompt=None,
    ):
        with self._lock:
            if instance.state in (States.RUNNING, States.PAUSED):
                client_server = self._get_client_server(instance)
                client_server.stop_instance(
                    instance.uuid,
                    graceful,
                    timeout,
                    shutdown_cmd,
                    username,
                    password,
                    prompt,
                )
                instance.state = States.STOPPED
            else:
                raise InstanceStateMisMatchError(
                    instance.state, (States.RUNNING, States.PAUSED))

    def pause_instance(self, instance):
        with self._lock:
            if instance.state == States.RUNNING:
                client_server = self._get_client_server(instance)
                client_server.pause_instance(instance.uuid)
                instance.state = States.PAUSED
            else:
                raise InstanceStateMisMatchError(instance.state, States.RUNNING)

    def continue_instance(self, instance):
        with self._lock:
            if instance.state == States.PAUSED:
                client_server = self._get_client_server(instance)
                client_server.continue_instance(instance.uuid)
                instance.state = States.RUNNING
            else:
                raise InstanceStateMisMatchError(instance.state, States.PAUSED)

    def undefine_instance(self, instance, free_mac_addresses=True):
        with self._lock:
            if instance.state == States.STOPPED:
                client_server = self._get_client_server(instance)
                client_server.cleanup_instance(instance.uuid, free_mac_addresses)
                instance.state = States.UNDEFINED
            else:
                raise InstanceStateMisMatchError(instance.state, States.STOPPED)

    def attach_instance_device(self, instance, dev_spec, monitor_id=None):
        with self._lock:
            if instance.state in (
                States.RUNNING,
                States.PAUSED,
            ):  # TODO: the States.STOPPED
                client_server = self._get_client_server(instance)
                # update the instance spec with the new device spec
                return client_server.attach_instance_device(
                    instance.uuid, dev_spec.to_json(), monitor_id
                )
            else:
                raise InstanceStateMisMatchError(
                    instance.state, (States.RUNNING, States.PAUSED))

    def detach_instance_device(self, instance, dev_spec, monitor_id=None):
        with self._lock:
            if instance.state == States.RUNNING:
                client_server = self._get_client_server(instance)
                # update the instance spec with the new device spec
                return client_server.detach_instance_device(
                    instance.uuid, dev_spec.to_json(), monitor_id
                )
            else:
                raise InstanceStateMisMatchError(instance.state, States.RUNNING)

    def get_monitor_consoles(self, instance):
        client_server = self._get_client_server(instance)
        return client_server.get_instance_consoles(instance.uuid, "monitor")

    def get_serial_consoles(self, instance):
        client_server = self._get_client_server(instance)
        return client_server.get_instance_consoles(instance.uuid, "serial")

    def get_process_info(self, instance, name):
        client_server = self._get_client_server(instance)
        return client_server.get_instance_process_info(instance.uuid, name)

    def get_pid(self, instance):
        client_server = self._get_client_server(instance)
        return client_server.get_instance_pid(instance.uuid)

    def check_capability_instance(self, instance, cap_name):
        client_server = self._get_client_server(instance)
        return client_server.check_instance_capability(instance.uuid, cap_name)

    def check_migration_parameter_instance(self, instance, param_name):
        client_server = self._get_client_server(instance)
        return client_server.check_instance_migration_parameter(
            instance.uuid, param_name
        )
