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
# Copyright 2013-2026 Intranet AG and contributors
# Author: Plamen Dimitrov <plamen.dimitrov@intra2net.com>

"""
Module for the LXC state management backend.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

from typing import Any

from virttest.utils_params import Params

from .setup import StateBackend


class LXCBackend(StateBackend):
    """Backend manipulating states as LXC container snapshots."""

    @classmethod
    def show(cls, params: Params, object: Any = None) -> None:
        """
        Return a list of available states of a specific type.

        All arguments match the base class.
        """
        raise NotImplementedError("Implement LXC states based on demand.")

    @classmethod
    def get(cls, params: Params, object: Any = None) -> None:
        """
        Retrieve a state disregarding the current changes.

        All arguments match the base class.
        """
        raise NotImplementedError("Implement LXC states based on demand.")

    @classmethod
    def set(cls, params: Params, object: Any = None) -> None:
        """
        Store a state saving the current changes.

        All arguments match the base class.
        """
        raise NotImplementedError("Implement LXC states based on demand.")

    @classmethod
    def unset(cls, params: Params, object: Any = None) -> None:
        """
        Remove a state with previous changes.

        All arguments match the base class.
        """
        raise NotImplementedError("Implement LXC states based on demand.")

    @classmethod
    def check_root(cls, params: Params, object: Any = None) -> None:
        """
        Check whether a root state or essentially the object exists.

        All arguments match the base class.
        """
        raise NotImplementedError("Implement LXC states based on demand.")

    @classmethod
    def set_root(cls, params: Params, object: Any = None) -> None:
        """
        Set a root state to provide object existence.

        All arguments match the base class.
        """
        raise NotImplementedError("Implement LXC states based on demand.")

    @classmethod
    def unset_root(cls, params: Params, object: Any = None) -> None:
        """
        Unset a root state to prevent object existence.

        All arguments match the base class and in addition:
        """
        raise NotImplementedError("Implement LXC states based on demand.")
