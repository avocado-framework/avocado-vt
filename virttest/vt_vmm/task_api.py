import logging

from virttest import utils_misc

from .objects import migration_exception
from .objects.instance_state import States as InstanceSates
from .objects.migration_state import MigrationState
from .objects.migration_task import LiveMigrationTaskLibvirt, LiveMigrationTaskQemu

LOG = logging.getLogger("avocado." + __name__)

MIGRATION_TASK_TIMEOUT = 3600


class MigrationTaskAPI(object):
    def __init__(self):
        pass

    @staticmethod
    def build_task(instance, destination, migration_config):
        if instance.kind == "qemu":
            return LiveMigrationTaskQemu(instance, destination, migration_config)
        elif instance.kind == "libvirt":
            return LiveMigrationTaskLibvirt(instance, destination, migration_config)
        else:
            raise NotImplementedError

    @staticmethod
    def execute_task(mig_task, timeout=MIGRATION_TASK_TIMEOUT):
        try:
            mig_task.execute()
        except (
            migration_exception.NoValidHost,
            migration_exception.InvalidHypervisorType,
            migration_exception.InvalidCPUInfo,
            migration_exception.UnableToMigrateToSelf,
            migration_exception.DestinationHypervisorTooOld,
            migration_exception.InvalidLocalStorage,
            migration_exception.InvalidSharedStorage,
            migration_exception.HypervisorUnavailable,
            migration_exception.InstanceInvalidState,
            migration_exception.MigrationPreCheckError,
        ) as ex:
            mig_task.status = MigrationState.ERROR
            raise migration_exception.MigrationError(str(ex))
        except Exception as ex:
            LOG.error(
                "Migration of instance %(instance_id)s to host"
                " %(dest)s unexpectedly failed.",
                mig_task.instance.uuid,
                mig_task.destination,
            )
            # instance.state = InstanceSates.ERROR
            mig_task.status = MigrationState.ERROR
            raise migration_exception.MigrationError(str(ex))

    # @staticmethod
    # def prepare_migrate_instance(mig_task):
    #     if mig_task.status is None:
    #         if not mig_task.prepare_migrate():
    #             raise
    #     else:
    #         raise
    #
    # @staticmethod
    # def post_migrate_instance(mig_task):
    #     if mig_task.status == MigrationState.POST_MIGRATING:
    #         if not mig_task.post_migrate():
    #             raise
    #     else:
    #         raise

    @staticmethod
    def cancel_task(mig_task):
        if mig_task.status in (MigrationState.MIGRATING, MigrationState.PRE_MIGRATING):
            if not mig_task.cancel_migrate():
                raise
        else:
            raise

    @staticmethod
    def resume_task(mig_task):
        if mig_task.status in (MigrationState.MIGRATING, MigrationState.PRE_MIGRATING):
            if not mig_task.resume_migrate():
                raise
        else:
            raise
