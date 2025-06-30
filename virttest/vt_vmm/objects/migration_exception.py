class MigrationError(Exception):
    pass


class UnableToMigrateToSelf(MigrationError):
    pass


class UnknownMigrationProtocolError(MigrationError):
    pass


class UnknownMigrationStatusError(MigrationError):
    pass


class InstanceInvalidState(MigrationError):
    pass


class InvalidHypervisorType(MigrationError):
    pass


class DestinationHypervisorTooOld(MigrationError):
    pass


class NoValidHost(MigrationError):
    pass


class InvalidCPUInfo(MigrationError):
    pass


class InvalidLocalStorage(MigrationError):
    pass


class InvalidSharedStorage(MigrationError):
    pass


class HypervisorUnavailable(MigrationError):
    pass


class ExceptMigrationStatusError(MigrationError):
    def __init__(self, except_status):
        self._except_status = except_status

    def __str__(self):
        return f"The exception migration status is {self._except_status}"


class MigrationPreCheckError(MigrationError):
    pass
