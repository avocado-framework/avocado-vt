# Copyright 2013-2021 Intranet AG and contributors
#
# avocado-i2n is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# avocado-i2n is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with avocado-i2n.  If not, see <http://www.gnu.org/licenses/>.

"""
Module for the VMNet state management backend.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

from typing import Any

from virttest.utils_params import Params

from .setup import StateBackend
from ..vmnet import VMNetwork


class VMNetBackend(StateBackend):
    """Backend manipulating network states as VMNet operations."""

    network_class = VMNetwork

    @classmethod
    def show(cls, params: Params, object: Any = None) -> list[str]:
        """
        Return a list of available states of a specific type.

        All arguments match the base class.
        """
        return ["default"]

    @classmethod
    def get(cls, params: Params, object: Any = None) -> None:
        """
        Retrieve a state disregarding the current changes.

        All arguments match the base class.
        """
        env = object
        env.start_ip_sniffing(params)
        vmn = cls.network_class(params, env)

        vmn.setup_host_bridges()
        vmn.setup_host_services()
        env.vmnet = vmn
        type(env).get_vmnet = lambda self: self.vmnet

    @classmethod
    def set(cls, params: Params, object: Any = None) -> None:
        """
        Store a state saving the current changes.

        All arguments match the base class.
        """
        pass

    @classmethod
    def unset(cls, params: Params, object: Any = None) -> None:
        """
        Remove a state with previous changes.

        All arguments match the base class.
        """
        pass

    @classmethod
    def check_root(cls, params: Params, object: Any = None) -> bool:
        """
        Check whether a root state or essentially the object exists.

        All arguments match the base class.
        """
        return True

    @classmethod
    def get_root(cls, params: Params, object: Any = None) -> None:
        """
        Get a root state or essentially due to pre-existence do nothing.

        :param params: configuration parameters
        :param object: object whose states are manipulated
        """
        cls.get(params, object=object)

    @classmethod
    def set_root(cls, params: Params, object: Any = None) -> None:
        """
        Set a root state to provide object existence.

        All arguments match the base class.
        """
        pass

    @classmethod
    def unset_root(cls, params: Params, object: Any = None) -> None:
        """
        Unset a root state to prevent object existence.

        All arguments match the base class and in addition:
        """
        pass
