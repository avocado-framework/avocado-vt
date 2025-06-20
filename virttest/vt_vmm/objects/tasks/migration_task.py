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


import json
import logging

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from virttest.vt_vmm.objects.exceptions import migration_exception
from virttest.vt_vmm.objects.states import instance_state
from virttest.vt_vmm.objects.states.migration_state import MigrationState
from virttest.vt_vmm.objects.tasks import task

LOG = logging.getLogger("avocado." + __name__)


class LiveMigrationTask(task.Task):
    def __init__(self, instance, destination, mig_config):
        """
        :param instance: The instance object will be migrated
        :type instance: virttest.vt_vmm.objects.Instance
        :param destination: The destination of the migration
        :type destination: Node.node
        :param mig_config: The mig configuration for the migration
        :type mig_config: dict
        """

        super(LiveMigrationTask, self).__init__(instance)
        self._source = instance.node
        self._destination = destination
        self._mig_config = mig_config
        self._source_orig_caps = {}
        self._dest_orig_caps = {}
        self._source_orig_params = {}
        self._dest_orig_params = {}
        self._status = MigrationState.ACCEPTED

    @property
    def destination(self):
        return self._destination

    def _check_source_instance_is_active(self):
        if self._instance.state not in (
            instance_state.States.RUNNING,
            instance_state.States.PAUSED,
        ):
            raise migration_exception.InstanceInvalidState()

    def _check_destination_is_not_source(self):
        if self._destination == self._source:
            raise migration_exception.UnableToMigrateToSelf()

    def _check_destination_has_enough_memory(self):
        avail_mem = self._destination.proxy.memory.get_usable_memory_size(512)
        instance_mem = self._instance.query_spec_info("memory.machine.size")
        if int(avail_mem) <= int(instance_mem):
            reason = (
                f"Unable to migrate instance_id({self._instance.uuid}) "
                f"to dest({self._destination.name}): "
                f"Lack of memory(host:{avail_mem} <= instance:{instance_mem})"
            )
            raise migration_exception.MigrationPreCheckError(reason)

    def _check_compatible_hypervisor(self):
        # TODO:
        # source_info = self._compute_api.get_hypervisor_info(self._source)
        # dest_info = self._compute_api.get_hypervisor_info(self._destination)
        #
        # if source_info["type"] != dest_info["type"]:
        #     raise migration_exception.InvalidHypervisorType
        #
        # if source_info["version"] > dest_info["version"]:
        #     raise migration_exception.DestinationHypervisorTooOld
        return

    def _check_requested_destination(self):
        """Performs basic pre-live migration checks for the forced host."""
        # TODO:
        return

    def prepare_migrate(self):
        """
        Prepare the environment to migrate from the source to destination.
        """
        LOG.info("Preparing the migration task.")
        if self.status == MigrationState.ACCEPTED:
            self._check_source_instance_is_active()
            self._check_destination_is_not_source()
            self._check_destination_has_enough_memory()
            self._check_compatible_hypervisor()
            self._check_requested_destination()
            self.status = MigrationState.PRE_MIGRATING
        else:
            raise migration_exception.ExceptMigrationStatusError(
                MigrationState.ACCEPTED
            )

    def _monitor_migration(self):
        """
        Monitor the migration to record the status and
        information during migration.

        :return:
        """
        LOG.info("Starting to monitoring of the migration")
        # TODO:

    def _migrate(self):
        """
        Migrate the instance by the hypervisor backend driver,
        e.g: qemu, libvirt, vmware, hyper.

        :return:
        """
        raise NotImplementedError

    def perform_migrate(self):
        """
        Start to migrate the instance from the source to the destination until
        it is completed.

        Raises:
            migration_exception.ExceptMigrationStatusError: _description_
        """
        LOG.info("Starting to execute the migration task.")
        if self.status == MigrationState.PRE_MIGRATING:
            self.status = MigrationState.MIGRATING
            self._migrate()
            self._monitor_migration()
            self.status = MigrationState.COMPLETED
        else:
            raise migration_exception.ExceptMigrationStatusError(
                MigrationState.PRE_MIGRATING
            )

    def post_migrate(self):
        """
        Post the environment of the migration.

        Raises:
            migration_exception.ExceptMigrationStatusError: _description_
        """
        LOG.info("Posting the migration task")
        if self.status in (MigrationState.COMPLETED, MigrationState.CANCELLED):
            if self.status == MigrationState.COMPLETED:
                self.status = MigrationState.POST_MIGRATING
                # Switch the instance's node
                self._instance.node = self._destination
            elif self.status == MigrationState.CANCELLED:
                # Do not switch the instance's node with cancelled status
                self.status = MigrationState.POST_MIGRATING
            # Switch the related resource from source to destination
            self.status = MigrationState.ACCEPTED
        else:
            raise migration_exception.ExceptMigrationStatusError(
                MigrationState.COMPLETED
            )

    def _execute(self):
        self.prepare_migrate()
        self.perform_migrate()
        self.post_migrate()

    def _cancel_migrate(self):
        raise NotImplementedError

    def cancel_migrate(self):
        LOG.info("Cancelling the migration task")
        if self.status in (MigrationState.MIGRATING, MigrationState.PRE_MIGRATING):
            ret = self._cancel_migrate()
            if ret:
                self.status = MigrationState.CANCELLED
            return ret
        else:
            raise migration_exception.ExceptMigrationStatusError(
                MigrationState.MIGRATING
            )

    def pause_migrate(self):
        raise NotImplementedError

    def _resume_migrate(self):
        raise NotImplementedError

    def resume_migrate(self):
        LOG.info("Resuming the migration task")
        if self.status == MigrationState.PAUSED_MIGRATING:
            ret = self._resume_migrate()
            if ret:
                self.status = MigrationState.MIGRATING
            return ret
        else:
            raise migration_exception.ExceptMigrationStatusError(
                MigrationState.MIGRATING
            )


class LiveMigrationTaskQemu(LiveMigrationTask):
    def __init__(self, instance, destination, mig_config):
        """

        :param instance: The instance
        :param destination: The destination node
        :param mig_config: the configuration for the migration
        {
            "flags": (), # e.g: [LIVE, OFFLINE, AUTO_CONVERGE, POSTCOPY, COMPRESSED, etc]
            "uri": {
                    "protocol": string, # e.g: tcp, rdma, unix, fd, etc
                    "address": string,
                    "port": integer,
                    },
            "capabilities": {
                            "source": {
                                        cap1: value1,
                                        cap2: value2,
                                        },
                            "destination": {
                                            cap1: value1,
                                            cap2: value2,
                                            },
                            },
            "parameters": {
                            "source": {
                                        param1: value1,
                                        param2: value2,
                                    },
                            "destination": {
                                            param1: value1,
                                            param2: value2,
                                            },
                        },
        }

        :type mig_config: dict
        """

        super(LiveMigrationTaskQemu, self).__init__(instance, destination, mig_config)

    def _compare_cpu(self, guest_cpu_info, host_cpu_info):
        """Check the host is compatible with the requested CPU"""
        # TODO:
        return

    def _check_requested_destination(self):
        # self._compare_cpu(guest_cpu_info, host_cpu_info)
        # TODO:
        return

    def _prepare_migrate_destination(self):
        LOG.info(
            f"Preparing the migration of the instance({self.instance.uuid}) "
            f"on the destination:({self.destination}) "
        )
        mig_params = dict()
        mig_params["flags"] = self._mig_config.get("flags")
        mig_params["uri"] = self._mig_config.get("uri")
        capabilities = self._mig_config.get("capabilities")
        if capabilities:
            mig_params["capabilities"] = capabilities.get("destination")

        parameters = self._mig_config.get("parameters")
        if parameters:
            mig_params["parameters"] = parameters.get("destination")

        backend = self._instance.kind
        # FIXME: convert it to json
        spec = self._instance.format_specs(format_type="json")
        return self._destination.proxy.virt.vmm.prepare_migrate_instance(
            self._instance.uuid, backend, spec, mig_params
        )

    def _perform_migrate_source(self, migrate_incoming_uri):
        LOG.info(
            f"Performing the migration of the instance({self.instance.uuid}) "
            f"on the source:({self._source}) "
        )
        mig_params = dict()
        mig_params["flags"] = self._mig_config.get("flags")
        mig_params["uri"] = self._mig_config.get("uri")
        mig_params["uri"]["address"] = migrate_incoming_uri.get("address")
        if "port" in migrate_incoming_uri:
            mig_params["uri"]["port"] = migrate_incoming_uri.get("port")
        capabilities = self._mig_config.get("capabilities")
        if capabilities:
            mig_params["capabilities"] = capabilities.get("source")

        parameters = self._mig_config.get("parameters")
        if parameters:
            mig_params["parameters"] = parameters.get("source")

        mig_params["no_wait_complete"] = self._mig_config.get("no_wait_complete", False)

        mig_ret, mig_info = self._source.proxy.virt.vmm.perform_migrate_instance(
            self._instance.uuid, mig_params
        )
        return mig_ret, json.loads(mig_info)

    def _finish_migrate_destination(self, mig_ret, timeout):
        LOG.info(
            f"Finishing the migration of the instance({self.instance.uuid}) "
            f"on the destination:({self.destination}) "
        )
        mig_params = dict()
        mig_params["flags"] = self._mig_config.get("flags")
        ret, mig_info = self._destination.proxy.virt.vmm.finish_migrate_instance(
            self._instance.uuid, mig_ret, mig_params
        )
        mig_info = json.loads(mig_info)
        return ret, mig_info

    def _confirm_migrate_source(self, inmig_ret):
        LOG.info(
            f"Confirming the migration of the instance({self.instance.uuid}) "
            f"on the source:({self._source}) "
        )
        mig_params = dict()
        mig_params["flags"] = self._mig_config.get("flags")
        self._source.proxy.virt.vmm.confirm_migrate_instance(
            self._instance.uuid, inmig_ret, mig_params
        )

    def __bind_and_allocate_port_resource(self, node):
        # bind and allocate the port resource to the node
        for net in self._instance.format_specs().get("nets"):
            nic_res_id = net["backend"]["props"]["port_source"]
            resmgr.update_resource(nic_res_id, {"bind": {"nodes": [node.name]}})
            resmgr.update_resource(nic_res_id, {"allocate": {"node_name": node.name}})

    def __unbind_and_release_port_resource(self, node):
        # unbind and release the port resource for the node
        for net in self._instance.format_specs().get("nets"):
            nic_res_id = net["backend"]["props"]["port_source"]
            resmgr.update_resource(nic_res_id, {"release": {"node_name": node.name}})
            resmgr.update_resource(nic_res_id, {"unbind": {"nodes": [node.name]}})

    def _migrate(self):
        self.__bind_and_allocate_port_resource(self._destination)

        # Dst: Get ready to accept incoming VM on the destination
        try:
            migrate_incoming_uri = self._prepare_migrate_destination()
        except Exception as e:
            LOG.error(str(e))
            self.__unbind_and_release_port_resource(self._destination)

        # Src: Start migration and wait for send completion
        try:
            mig_ret, mig_info = self._perform_migrate_source(migrate_incoming_uri)
        except Exception as mig_err:
            self.__unbind_and_release_port_resource(self._destination)
            raise mig_err

        # Dst: Wait for recv completion and check status
        #      Kill off VM if failed, resume if success
        if "cancelled" not in mig_info.get("status"):
            inmig_ret, inmig_info = self._finish_migrate_destination(
                mig_ret, timeout=1200
            )
            if not mig_ret:
                self.__unbind_and_release_port_resource(self._destination)
                return False, mig_info

            # Src: Kill off VM if success, resume if failed
            self._confirm_migrate_source(inmig_ret)
            self.__unbind_and_release_port_resource(self._source)
            return True, mig_info
        else:
            self.__unbind_and_release_port_resource(self._destination)

    def _cancel_migrate(self):
        return self._source.proxy.virt.vmm.cancel_migrate_instance(self._instance.uuid)

    def _resume_migrate(self):
        self._source.proxy.virt.vmm.resume_migrate_instance(self._instance.uuid)


class LiveMigrationTaskLibvirt(LiveMigrationTask):
    def __init__(self, instance, destination, mig_config):
        super(LiveMigrationTaskLibvirt, self).__init__(
            instance, destination, mig_config
        )

    def _migrate(self):
        """
        Migrate the vm to another host by sending command
        e.g: "virsh migrate --live GuestName DestinationURL"
        """
        pass

    def _cancel_migrate(self):
        pass

    def _resume_migrate(self):
        pass
