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


class InstanceError(Exception):
    pass


class InstanceInvalidState(InstanceError):
    pass


class InstanceSpecError(InstanceError):
    pass


class InstanceStateError(InstanceError):
    pass


class InstanceStateMisMatchError(InstanceStateError):
    def __init__(self, error_state, except_state):
        self._error_state = error_state
        self._except_state = except_state

    def __str__(self):
        return (f"The excepted state of the instance is {self._except_state}, "
                f"not {self._error_state}")
