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
VMNode object for the vmnet utility.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
This class wraps up the functionality shared among the interfaces of
the same platform like session management, etc.

INTERFACE
------------------------------------------------------

"""

from typing import Callable
import logging as log

from aexpect.client import RemoteSession
from virttest.utils_params import Params
from virttest.qemu_vm import VM

logging = log.getLogger("avocado.job." + __name__)


class VMNode(object):
    """Get the vmnode class - a collection of interfaces sharing the same platform."""

    """Structural properties"""

    @property
    def interfaces(self) -> dict[str, "VMInterface"]:
        """Get a collection of interfaces the vm node represents."""
        return self._interfaces

    @property
    def ephemeral(self) -> bool:
        """
        Check if the vm node is ephemeral.

        returns: whether the vm node is ephemeral (spawned in a network).
        """
        return self._ephemeral

    """Platform properties"""

    def platform(self, value: VM = None) -> VM | None:
        """Get a reference to the virtual machine object whose network configuration is represented by the vm node."""
        if value is not None:
            self._platform = value
            return None
        else:
            return self._platform

    platform = property(fget=platform, fset=platform)

    def name(self, value: str = None) -> str | None:
        """Get a proxy reference to the vm name."""
        if value is not None:
            self._platform.name = value
            return None
        else:
            return self._platform.name

    name = property(fget=name, fset=name)

    @property
    def params(self) -> Params:
        """
        Get a proxy reference to the vm params.

        .. note:: this is just a shallow copy to preserve the hierarchy:
            network level params = test level params -> vmnode level params = test object params
            -> interface level params = rarely used outside of the vm network
        """
        return self._platform.params

    def remote_sessions(
        self, value: list[RemoteSession] = None
    ) -> list[RemoteSession] | None:
        """Get a proxy reference to the vm sessions."""
        if value is not None:
            self._platform.remote_sessions = value
            return None
        else:
            return self._platform.remote_sessions

    remote_sessions = property(fget=remote_sessions, fset=remote_sessions)

    def last_session(self, value: RemoteSession = None) -> RemoteSession | None:
        """
        Get a pointer to the last created vm session.

        Used to facilitate the frequent access to a single session.
        """
        if value is not None:
            self._last_session = value
            return None
        else:
            return self._last_session

    last_session = property(fget=last_session, fset=last_session)

    def __init__(self, platform: VM, ephemeral: bool = False) -> None:
        """
        Construct a vm node from a vm platform.

        :param platform: the vm platform that communicates in the vm network
        :param ephemeral: whether the node is ephemeral (spawned in a network)
        """
        self._interfaces = {}

        self._ephemeral = ephemeral

        self._platform = platform
        self._last_session = None

    def __repr__(self) -> str:
        """Provide a representation of the object."""
        vm_tuple = (self.name, len(self.remote_sessions))
        return "[node] name='%s', sessions='%s'" % vm_tuple

    def check_interface(
        self, condition: Callable[["VMInterface"], bool]
    ) -> "VMInterface | None":
        """
        Check whether one of node's interfaces satisfies a boolean condition.

        :param condition: condition to try each interface on
        :returns: the first interface satisfying the provided criteria or None
        """
        for interface in self.interfaces.values():
            if condition(interface):
                return interface
        return None

    def get_single_interface(self) -> "VMInterface":
        """
        Get a single (first) interface of the node.

        This is useful for nodes having just one interface.
        """
        return list(self.interfaces.values())[0]

    def get_session(self, serial: bool = False) -> RemoteSession:
        """
        Obtain a session from a vmnode by performing the basic network login.

        :param serial: whether to use serial connection
        """
        self.platform.verify_alive()
        timeout = float(self.params.get("login_timeout", 240))
        logging.info("Log in to %s with timeout %s", self.name, timeout)
        if serial:
            self.last_session = self.platform.wait_for_serial_login(timeout=timeout)
        else:
            self.last_session = self.platform.wait_for_login(timeout=timeout)
        # TODO: possibly use the original vm session list or remove this wrapper entirely
        self.platform.session = self.last_session
        return self.last_session
