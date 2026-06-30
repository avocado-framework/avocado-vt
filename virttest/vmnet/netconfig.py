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
Network configuration object for the VM network.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
It contains the network configuration, offers network services like
IP address allocation, translation, and validation, and consists
of Interface objects that share this network configuration.

INTERFACE
------------------------------------------------------

"""

from typing import Any
import logging as log

import ipaddress

from .interface import VMInterface
from avocado.core import exceptions

logging = log.getLogger("avocado.job." + __name__)


class VMNetconfig(object):
    """Get the netconfig class - a collection of interfaces sharing the same network configuration."""

    """Structural properties"""

    @property
    def interfaces(self) -> dict[Any, VMInterface]:
        """
        Get a collection of interfaces the netconfig represents.

        ..todo:: The key type should be str but using the same method and property name confuses
            our automation in some places and not in others.
        """
        return self._interfaces

    """Configuration properties"""

    def netdst(self, value: str = None) -> str | None:
        """
        Get the bridge where Qemu will redirect the packets.

        Plays the role of the network connectivity skeleton.
        """
        if value is not None:
            self._netdst = value
            return None
        else:
            return self._netdst

    netdst = property(fget=netdst, fset=netdst)

    def netmask(self, value: str = None) -> str | None:
        """Get the netmask used by the participating network interfaces."""
        if value is not None:
            self._netmask = value
            return None
        else:
            return self._netmask

    netmask = property(fget=netmask, fset=netmask)

    def mask_bit(self, value: str = None) -> str | None:
        """Get the netmask bit used by the participating network interfaces."""
        if value is not None:
            interface = ipaddress.ip_interface("%s/%s" % (self.net_ip, value))
            self.netmask = str(interface.network.netmask)
            return None
        else:
            # producing the mask bit from the netmask is not provided by
            # Python so reimplement it here
            if self.netmask is None:
                return None
            netmask = self.netmask.split(".")
            binary_str = ""
            for octet in netmask:
                binary_str += bin(int(octet))[2:].zfill(8)
            return str(len(binary_str.rstrip("0")))

    mask_bit = property(fget=mask_bit, fset=mask_bit)

    def gateway(self, value: str = None) -> str | None:
        """Get the gateway ip used by the participating network interfaces."""
        if value is not None:
            self._gateway = value
            return None
        else:
            return self._gateway

    gateway = property(fget=gateway, fset=gateway)

    def net_ip(self, value: str = None) -> str | None:
        """Get the network ip used by the participating network interfaces."""
        if value is not None:
            self._net_ip = value
            return None
        else:
            return self._net_ip

    net_ip = property(fget=net_ip, fset=net_ip)

    def host_ip(self, value: str = None) -> str | None:
        """IP of the host for the virtual machine if it participates in the local network (and therefore in the netcofig)."""
        if value is not None:
            self._host_ip = value
            return None
        else:
            return self._host_ip

    host_ip = property(fget=host_ip, fset=host_ip)

    @property
    def range(self) -> dict[int, bool]:
        """
        IP range of addresses that can be allocated to joining vms (new interfaces that join the netconfig).

        To set a different ip_start and ip_end, i.e. different boundaries,
        use the setter of this property.

        .. note:: Used for any DHCP configuration.
        """
        return self._range

    @property
    def ip_start(self) -> str:
        """Beginning of the IP range."""
        minint = 0 if len(self.range) == 0 else min(self.range.keys())
        return str(ipaddress.IPv4Address(self.net_ip) + minint)

    @property
    def ip_end(self, value: str = None) -> str:
        """End of the IP range."""
        maxint = 0 if len(self.range) == 0 else max(self.range.keys())
        return str(ipaddress.IPv4Address(self.net_ip) + maxint)

    def domain(self, value: str = None) -> str | None:
        """
        DNS domain name for the local network.

        .. note:: Used for host-based DNS configuration.
        """
        if value is not None:
            self._domain = value
            return None
        else:
            return self._domain

    domain = property(fget=domain, fset=domain)

    def forwarder(self, value: str = None) -> str | None:
        """
        DNS forwarder address for the local network.

        .. note:: Used for host-based DNS configuration.
        """
        if value is not None:
            self._forwarder = value
            return None
        else:
            return self._forwarder

    forwarder = property(fget=forwarder, fset=forwarder)

    def rev(self, value: str = None) -> str | None:
        """
        DNS reverse lookup table name for the local network.

        .. note:: Used for host-based DNS configuration.
        """
        if value is not None:
            self._rev = value
            return None
        else:
            return self._rev

    rev = property(fget=rev, fset=rev)

    def view(self, value: str = None) -> str | None:
        """
        DNS view name for the local network.

        .. note:: Used for host-based DNS configuration.
        """
        if value is not None:
            self._view = value
            return None
        else:
            return self._view

    view = property(fget=view, fset=view)

    def ext_netdst(self, value: str = None) -> str | None:
        """
        External network destination to which we route after network translation.

        .. note:: Used for host-based NAT configuration.
        """
        if value is not None:
            self._ext_netdst = value
            return None
        else:
            return self._ext_netdst

    ext_netdst = property(fget=ext_netdst, fset=ext_netdst)

    def __init__(self) -> None:
        """Construct a nonconfigured netconfig."""
        self._interfaces: dict[str, VMInterface] = {}

        self._netdst = None
        self._netmask = None
        self._gateway = None
        self._net_ip = None
        self._host_ip = None

        self._range = {}
        self._domain = None
        self._forwarder = None
        self._rev = None
        self._view = None

        self._ext_netdst = None

    def __repr__(self) -> str:
        """Provide a representation of the object."""
        net_tuple = (self.net_ip, self.netmask, self.netdst)
        return "[net] addr='%s', netmask='%s', netdst='%s'" % net_tuple

    def _get_network_ip(self, ip: str, bit: int) -> str:
        interface = ipaddress.ip_interface("%s/%s" % (ip, bit))
        return str(interface.network.network_address)

    def from_interface(self, interface: VMInterface) -> None:
        """
        Construct all netconfig parameters from the provided interface.

        Alternatively reset them with respect to that interface if they were already set.

        :param interface: reference interface for the configuration
        """
        # main
        self.netdst = interface.params.get("netdst")
        self.netmask = interface.params["netmask"]
        self.gateway = interface.params.get("ip_provider", "0.0.0.0")
        self.net_ip = self._get_network_ip(interface.ip, self.mask_bit)
        self.host_ip = interface.params.get("host")

        # DHCP specific
        pool_range = interface.params.get("range", "100-200").split("-")
        self._range = {
            i: False for i in range(int(pool_range[0]), int(pool_range[1]) + 1)
        }

        # DNS specific
        self.domain = interface.params.get("domain_provider")
        self.forwarder = interface.params.get("default_dns_forwarder")
        # TODO: generate this more appropriately
        self.rev = ".".join(reversed(self.net_ip.split(".")[:-1]))
        if self.domain is not None:
            self.view = "%s-%s" % (self.domain, self.net_ip)

        # NAT specific
        self.ext_netdst = interface.params.get("postrouting_netdst")

    def add_interface(self, interface: VMInterface) -> None:
        """
        Add an interface to the netconfig.

        Perform the necessary registrations and finishing
        with validation of the interface configuration.

        :param interface: interface to add to the netconfig
        """
        self.interfaces[interface.ip] = interface
        self.interfaces[interface.ip].netconfig = self
        self.validate()

    def has_interface(self, interface: VMInterface) -> bool:
        """
        Check whether an interface already belongs to the netconfig.

        Checking is done through both IP and actual attachment (to counter same IP range netconfigs).

        :param interface: interface to check in the netconfig
        :returns: whether the interface is already present in the netconfig
        """
        return (
            interface.ip in self.interfaces.keys()
            and self.interfaces[interface.ip] == interface
        )

    def can_add_interface(self, interface: VMInterface) -> bool:
        """
        Check if an interface can be added to the netconfig based on its desired IP address.

        Throw exceptions if it is already present or the netmask does not coincide (misconfiguration errors).

        :param interface: interface to add to the netconfig
        :returns: whether the interface can be added
        :raises: :py:class:`exceptions.IndexError` if interface is already present or incompatible
        """
        if self.has_interface(interface):
            raise IndexError(
                "Interface %s already present in the "
                "network %s" % (interface.ip, self.net_ip)
            )
        interface_net_ip = self._get_network_ip(interface.ip, self.mask_bit)
        if (
            interface_net_ip == self.net_ip
            and interface.params["netmask"] != self.netmask
        ):
            raise IndexError(
                "Interface %s has different netmask %s from the "
                "network %s (%s)"
                % (interface.ip, interface.params["netmask"], self.net_ip, self.netmask)
            )
        return interface_net_ip == self.net_ip

    def validate(self) -> None:
        """
        Check for sanity of the netconfigs parameters.

        :raises: :py:class:`exceptions.TestError` if the validation fails
        """
        logging.debug("Validating the parameter derived netconfig %s", self)

        # validate network addresses
        addresses = {}
        # NOTE: it is possible that either the host was never defined or was later on disabled
        if self.host_ip is not None and self.host_ip != "":
            addresses["host"] = ipaddress.ip_interface(
                "%s/%s" % (self.host_ip, self.mask_bit)
            )
        assert self.ip_start is not None
        assert self.ip_end is not None
        addresses["ip_start"] = ipaddress.ip_interface(
            "%s/%s" % (self.ip_start, self.mask_bit)
        )
        addresses["ip_end"] = ipaddress.ip_interface(
            "%s/%s" % (self.ip_end, self.mask_bit)
        )

        own = ipaddress.ip_interface("%s/%s" % (self.net_ip, self.mask_bit))
        for key in addresses.keys():
            if addresses[key] not in own.network:
                raise exceptions.TestError(
                    "The predefined %s %s is not in the netconfig"
                    " %s" % (key, addresses[key], self.net_ip)
                )

        # validate interfaces
        for interface in self.interfaces.values():
            assert interface.netconfig == self
            assert self.interfaces[interface.ip] == interface

            ip = ipaddress.ip_interface("%s/%s" % (interface.ip, self.mask_bit))
            if ip not in own.network:
                raise exceptions.TestError(
                    "The interface with ip %s is not in the netconfig"
                    " %s" % (ip, self.net_ip)
                )

    def get_allocatable_address(self) -> str:
        """Return the next IP address in the pool of available IPs that can be used by DHCP clients in the network."""
        for val in self.range:
            if self.range[val] is False:
                self.range[val] = True
                new_address = val
                break
        else:
            raise IndexError("IP address range (%d) exhausted." % len(self.range))
        net_ip = ipaddress.IPv4Address(str(self.net_ip))
        return str(ipaddress.IPv4Address(str(net_ip + new_address)))

    def translate_address(self, ip: str, nat_ip: str) -> str:
        """Return the NAT translated IP of an interface.

        Alternatively return the NAT translated IP of an interface masked by a desired network address.
        :param interface: interface to translate
        :param nat_ip: NATed IP to use for reference
        :returns: the translated IP of the interface
        """
        source_ip = ipaddress.IPv4Address(ip)
        source_part = int(source_ip) - int(ipaddress.IPv4Address(str(self.net_ip)))
        target_iface = ipaddress.ip_interface("%s/%s" % (nat_ip, self.mask_bit))
        target_part = int(target_iface.network.network_address)
        translated_ip = ipaddress.IPv4Address(source_part + target_part)
        return str(translated_ip)
