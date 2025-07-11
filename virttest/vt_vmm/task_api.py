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

from virttest.vt_vmm.objects.states.migration_state import MigrationState
from virttest.vt_vmm.objects.tasks.migration_task import (
    LiveMigrationTaskLibvirt,
    LiveMigrationTaskQemu,
)

from .objects.exceptions import migration_exception

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
            raise NotImplementedError(
                f"Not supported the virtualization test backend: {instance.kind}"
            )

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
                f"Migration of instance {mig_task.instance.uuid} to host "
                f"{mig_task.destination} unexpectedly failed"
            )
            mig_task.status = MigrationState.ERROR
            raise migration_exception.MigrationError(str(ex))

    @staticmethod
    def cancel_task(mig_task):
        return mig_task.cancel_migrate()

    @staticmethod
    def resume_task(mig_task):
        return mig_task.resume_migrate()
