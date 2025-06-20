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
