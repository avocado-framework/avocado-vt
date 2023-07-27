import logging

from .compute_api import ComputeAPI
from .instance_api import InstanceAPI
from .objects import instance_state

from .objects.migration_state import MigrationState

from .objects.instance_exception import InstanceInvalidState

from .objects.migration_exception import UnableToMigrateToSelf


LOG = logging.getLogger("avocado." + __name__)


class MigrateAPI(object):
    def __init__(self):
        self._instance_api = InstanceAPI()
        self._compute_node_api = ComputeAPI()

    def _do_pre_qemu_migration(self, instance, destination, migration_config):
        pass

    def _do_pre_libvirt_migration(self, instance, dest, migration, migrate_data):
        raise NotImplementedError

    @staticmethod
    def _check_instance_is_active(instance):
        LOG.info("Checking if the instance is active")
        if instance.state not in (
            instance_state.States.RUNNING,
            instance_state.States.PAUSED,
        ):
            raise InstanceInvalidState()

    @staticmethod
    def _check_destination_is_not_source(source, destination):
        LOG.info("Checking if the source and destination is the same")
        if destination == source:
            raise UnableToMigrateToSelf()

    @staticmethod
    def _check_destination_has_enough_memory(destination):
        LOG.info("Checking if the destination has enough memory")
        pass

    def pre_migrate(self, instance, dest, migration, migrate_data):
        """
        Prepare the jobs before doing live migration, such as allocate the
        resource of VM instance in advance
        it will do the rollback job if we failed in this stage.

        :param instance:
        :param dest:
        :param migration:
        :param migrate_data:
        :return:
        """

        self._check_instance_is_active(instance)
        self._check_destination_is_not_source(instance.node, dest)
        self._check_destination_has_enough_memory(dest)

        if instance.kind == "qemu":
            self._do_pre_qemu_migration(instance, dest, migration, migrate_data)
        elif instance.kind == "libvirt":
            self._do_pre_libvirt_migration(instance, dest, migration, migrate_data)
        else:
            raise ValueError(f"No support the type {instance.kind} instance")

    def _do_live_qemu_migration(self, instance, dest, migration, migrate_data):
        pass

    def _do_live_libvirt_migration(self, instance, dest, migration, migrate_data):
        pass

    def _do_live_migration(self, instance, dest, migration, migrate_data):
        """
        Execute and finish the live migration job for the VM instance.
        it will do the rollback job if we failed in this stage.

        :param instance:
        :param dest:
        :param migration:
        :param migrate_data:
        :return:
        """

        self._set_migration_status(migration, MigrationState.MIGRATING)
        LOG.info(f"migrating instance to {dest.node}")
        if instance.kind == "qemu":
            self._do_live_qemu_migration(instance, dest, migration, migrate_data)
        elif instance.kind == "libvirt":
            self._do_live_libvirt_migration(instance, dest, migration, migrate_data)
        else:
            raise ValueError(f"No support the type {instance.kind} instance")

    def post_migrate(self, instance, dest, migration, migrate_data):
        """
        Do the cleanup job after migrate the VM instance completely, such as
        cleaning up the related resource of the VM instance.

        :param instance:
        :param dest:
        :param migration:
        :param migrate_data:
        :return:
        """
        self._set_migration_status(migration, MigrationState.POST_MIGRATING)

    @staticmethod
    def _set_migration_status(migration, status):
        migration.status = status

    @staticmethod
    def _get_migration_status(migration):
        return migration.status

    def live_migration(self, instance, destination, migration_config):
        pass

    def cancel_migration(self, instance):
        pass

    def resume_migration(self, instance):
        pass

    def get_migrate_info(self, instance):
        pass
