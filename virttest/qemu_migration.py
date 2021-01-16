"""
Interface for QEMU migration.
"""

from virttest.qemu_capabilities import MigrationParams
from virttest.qemu_capabilities import Flags

from virttest.utils_numeric import normalize_data_size


def set_downtime(vm, value):
    """
    Set maximum tolerated downtime for migration.

    :param vm: VM object.
    :param value: Maximum downtime in seconds.
    :return: Output of command.
    """
    if (vm.check_capability(Flags.MIGRATION_PARAMS) and
            vm.check_migration_parameter(MigrationParams.DOWNTIME_LIMIT)):
        return vm.monitor.set_migrate_parameter('downtime-limit', value * 1000)
    return vm.monitor.migrate_set_downtime(value)


def set_speed(vm, value):
    """
    Set maximum speed for migration.

    :param vm: VM object.
    :param value: Speed in bytes/sec.
    :return: Output of command.
    """
    if (vm.check_capability(Flags.MIGRATION_PARAMS) and
            vm.check_migration_parameter(MigrationParams.MAX_BANDWIDTH)):
        value = int(normalize_data_size(value, 'B'))
        return vm.monitor.set_migrate_parameter('max-bandwidth', value)
    return vm.monitor.migrate_set_speed(value)


def set_cache_size(vm, value):
    """
    Set cache size for migration.

    :param vm: VM object.
    :param value: Cache size to set.
    :return: Output of command.
    """
    if (vm.check_capability(Flags.MIGRATION_PARAMS) and
            vm.check_migration_parameter(MigrationParams.XBZRLE_CACHE_SIZE)):
        return vm.monitor.set_migrate_parameter('xbzrle-cache-size', value)
    return vm.monitor.set_migrate_cache_size(value)
