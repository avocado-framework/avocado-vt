# Copyright 2013-2020 Intranet AG and contributors
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
Interface object for the vmnet utility.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
This is the basic building block of the vm network. Interfaces are grouped
in nodes (the virtual machines they belong to) and in netconfigs (the
local networks they define together).

INTERFACE
------------------------------------------------------

"""

from virttest.utils_params import Params

from .node import VMNode


class VMInterface(object):
    """Get the interface class."""

    """Structural properties"""

    def node(self, value: VMNode = None) -> VMNode | None:
        """Get a reference to the node the interface belongs to."""
        if value is not None:
            self._node = value
            return None
        else:
            return self._node

    node = property(fget=node, fset=node)

    def netconfig(self, value: "VMNetconfig" = None) -> "VMNetconfig | None":
        """Get a reference to the netconfig the interface belongs to."""
        if value is not None:
            self._netconfig = value
            return None
        else:
            return self._netconfig

    netconfig = property(fget=netconfig, fset=netconfig)

    @property
    def params(self) -> Params:
        """Use as the interface filtered test parameters."""
        return self._params

    """Configuration properties"""

    def mac(self, value: str = None) -> str | None:
        """MAC address used by the network interface."""
        if value is not None:
            self._mac = value
            return None
        else:
            return self._mac

    mac = property(fget=mac, fset=mac)

    def ip(self, value: str = None) -> str | None:
        """IP address used by the network interface."""
        if value is not None:
            self._ip = value
            return None
        else:
            return self._ip

    ip = property(fget=ip, fset=ip)

    """Interface properties"""

    def name(self, value: str = None) -> str | None:
        """Name for the interface."""
        if value is not None:
            self._name = value
            return None
        else:
            return self._name

    name = property(fget=name, fset=name)

    def __init__(self, name: str, params: Params) -> None:
        """
        Construct an interface with configuration from the parameters.

        :param params: configuration parameters
        """
        self._name = name

        self._node = None
        self._netconfig = None
        self._params = params

        self._mac = params["mac"]
        self._ip = params["ip"]

    def __repr__(self) -> str:
        """Provide a representation of the object."""
        vm_name = "none" if self.node is None else self.node.name
        net_name = "none" if self.netconfig is None else self.netconfig.net_ip
        iface_tuple = (self.name, self.ip, self.mac, vm_name, net_name)
        return (
            "[iface] name='%s', addr='%s', mac='%s' platform='%s' netconfig='%s'"
            % iface_tuple
        )
