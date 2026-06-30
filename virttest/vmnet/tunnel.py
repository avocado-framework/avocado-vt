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
# Copyright 2013-2020 Intranet AG and contributors
# Author: Plamen Dimitrov <plamen.dimitrov@intra2net.com>

"""
Tunnel object for the vmnet utility.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
This class wraps up the utilities for managing tunnels.

The parameters parsed at each vm are used as overwrite dictionary and
and missing ones are generated for the full configuration of the tunnel.

INTERFACE
------------------------------------------------------

"""

from typing import Any
import logging as log

from virttest.utils_params import Params

from .netconfig import VMNetconfig
from .interface import VMInterface
from .node import VMNode

logging = log.getLogger("avocado.job." + __name__)


class VMTunnel(object):
    """Get the tunnel class."""

    """Structural properties"""

    def left(self, value: VMNode = None) -> VMNode | None:
        """Get a reference to the left node of the tunnel."""
        if value is not None:
            self._left = value
            return None
        else:
            return self._left

    left = property(fget=left, fset=left)

    def right(self, value: VMNode = None) -> VMNode | None:
        """Get a reference to the right node of the tunnel."""
        if value is not None:
            self._right = value
            return None
        else:
            return self._right

    right = property(fget=right, fset=right)

    def left_iface(self, value: VMInterface = None) -> VMInterface | None:
        """Get a reference to the left interface of the tunnel."""
        if value is not None:
            self._left_iface = value
            return None
        else:
            return self._left_iface

    left_iface = property(fget=left_iface, fset=left_iface)

    def right_iface(self, value: VMInterface = None) -> VMInterface | None:
        """Get a reference to the right interface of the tunnel."""
        if value is not None:
            self._right_iface = value
            return None
        else:
            return self._right_iface

    right_iface = property(fget=right_iface, fset=right_iface)

    def left_net(self, value: VMNetconfig = None) -> VMNetconfig | None:
        """Get a reference to the left netconfig of the tunnel."""
        if value is not None:
            self._left_net = value
            return None
        else:
            return self._left_net

    left_net = property(fget=left_net, fset=left_net)

    def right_net(self, value: VMNetconfig = None) -> VMNetconfig | None:
        """Get a reference to the right netconfig of the tunnel."""
        if value is not None:
            self._right_net = value
            return None
        else:
            return self._right_net

    right_net = property(fget=right_net, fset=right_net)

    @property
    def left_params(self) -> Params:
        """Tunnel generated left side parameters."""
        return self.left.params.object_params(self.name)

    @property
    def right_params(self) -> Params:
        """Tunnel generated right side parameters."""
        return self.right.params.object_params(self.name)

    @property
    def params(self) -> Params:
        """Tunnel generated test parameters."""
        return self._params

    """Connection properties"""

    def name(self, value: str = None) -> str | None:
        """Name for the connection."""
        if value is not None:
            self._name = value
            return None
        else:
            return self._name

    name = property(fget=name, fset=name)

    def __init__(
        self,
        name: str,
        node1: VMNode,
        node2: VMNode,
        local1: dict[str, str] = None,
        remote1: dict[str, str] = None,
        peer1: dict[str, str] = None,
        auth: dict[str, str] = None,
    ) -> None:
        """
        Construct the full set of required tunnel parameters for a given tunnel left configuration.

        That are not already defined in the parameters of the two vms (left 'node1' with right 'node2').

        :param name: name of the tunnel
        :param node1: left side node of the tunnel
        :param node2: right side node of the tunnel
        :param local1: left local configuration with at least one key 'type' with value 'nic'
                       for left-site (could be used for site-to-site or site-to-point tunnels)
                       or 'internetip' for left-point (for point-to-site or point-to-point tunnels)
                       or 'custom' for left-site or left-point that is not a LAN (e.g. for tunnel
                       forwarding of another tunneled remote net)
        :param remote1: left remote configuration with at least one key 'type' with value 'custom'
                        for right-site (could be used for site-to-site or point-to-site tunnels) or
                        'externalip' for right-point (for site-to-point or point-to-point tunnels)
                        or 'modeconfig' for special right-point (using a ModeConfig connection for
                        a right road warrior)
        :param peer1: left peer configuration with at least one key 'type' with value 'ip' for no
                      NAT along the tunnel (the peer having a public IP) or 'dynip' for a road
                      warrior right end point (the peer is behind NAT and its IP is changing)
        :param auth: authentication configuration with at least one key 'type' with value in
                     "pubkey", "psk", "none" and the rest of the keys providing type details
        :raises: :py:class:`ValueError` if some of the supplied configuration is not valid

        The right side `local2`, `remote2`, `peer2` configuration is determined from the left side.

        If a PSK (pre-shared secret) authentication type is specified, the relevant additional
        options are `psk` for the secret word, `left_id` and `right_id` for the identification
        type to be used on each side (either IP for empty id or any user-defined id).
        """
        logging.info(
            "Preparing tunnel parameters for each of %s and %s", node1.name, node2.name
        )
        if local1 is None:
            local1 = {"type": "nic", "nic": "lan_nic"}
        if remote1 is None:
            remote1 = {"type": "custom", "nic": "lan_nic"}
        if peer1 is None:
            peer1 = {"type": "ip", "nic": "internet_nic"}
        local2, remote2, peer2 = self._get_peer_variant(local1, remote1, peer1)
        params = Params()

        # main parameters
        params["vpnconn_%s_%s" % (name, node1.name)] = name
        params["vpnconn_%s_%s" % (name, node2.name)] = name
        params["vpn_side_%s_%s" % (name, node1.name)] = "left"
        params["vpn_side_%s_%s" % (name, node2.name)] = "right"
        params["vpnconn_lan_type_%s_%s" % (name, node1.name)] = local1["type"].upper()
        params["vpnconn_lan_type_%s_%s" % (name, node2.name)] = local2["type"].upper()
        params["vpnconn_remote_type_%s_%s" % (name, node1.name)] = remote1[
            "type"
        ].upper()
        params["vpnconn_remote_type_%s_%s" % (name, node2.name)] = remote2[
            "type"
        ].upper()

        if local1["type"] == "nic":
            netconfig1 = node1.interfaces[
                node1.params[local1.get("nic", "lan_nic")]
            ].netconfig
            params["vpnconn_lan_net_%s_%s" % (name, node1.name)] = netconfig1.net_ip
            params["vpnconn_lan_netmask_%s_%s" % (name, node1.name)] = (
                netconfig1.netmask
            )
            params["vpnconn_remote_net_%s_%s" % (name, node2.name)] = netconfig1.net_ip
            params["vpnconn_remote_netmask_%s_%s" % (name, node2.name)] = (
                netconfig1.netmask
            )
        elif local1["type"] == "internetip":
            netconfig1 = None
        elif local1["type"] == "custom":
            # "custom" configuration does no guarantee pre-existing netconfig like "nic"
            # so create an address/netmask only netconfig to match against for compatibility
            netconfig1 = VMNetconfig()
            netconfig1.net_ip = local1["lnet"]
            netconfig1.netmask = local1["lmask"]
            params["vpnconn_lan_net_%s_%s" % (name, node1.name)] = local1["lnet"]
            params["vpnconn_lan_netmask_%s_%s" % (name, node1.name)] = local1["lmask"]
        else:
            raise ValueError(
                "Invalid choice of left local type '%s', must be one of"
                " 'nic', 'internetip', 'custom'" % local1["type"]
            )
        if remote1["type"] == "custom":
            if local1["type"] == "custom":
                netconfig2 = VMNetconfig()
                netconfig2.net_ip = local1["rnet"]
                netconfig2.netmask = local1["rmask"]
                params["vpnconn_lan_net_%s_%s" % (name, node2.name)] = local1["rnet"]
                params["vpnconn_lan_netmask_%s_%s" % (name, node2.name)] = local1[
                    "rmask"
                ]
            else:
                netconfig2 = node2.interfaces[
                    node2.params[remote1.get("nic", "lan_nic")]
                ].netconfig
                params["vpnconn_lan_net_%s_%s" % (name, node2.name)] = netconfig2.net_ip
                params["vpnconn_lan_netmask_%s_%s" % (name, node2.name)] = (
                    netconfig2.netmask
                )
            params["vpnconn_remote_net_%s_%s" % (name, node1.name)] = netconfig2.net_ip
            params["vpnconn_remote_netmask_%s_%s" % (name, node1.name)] = (
                netconfig2.netmask
            )
        elif remote1["type"] == "externalip":
            netconfig2 = None
        elif remote1["type"] == "modeconfig":
            netconfig2 = None
            params["vpnconn_remote_modeconfig_ip_%s_%s" % (name, node1.name)] = remote1[
                "modeconfig_ip"
            ]
        else:
            raise ValueError(
                "Invalid choice of left remote type '%s', must be one of"
                " 'custom', 'externalip', or 'modeconfig'" % remote1["type"]
            )

        # road warrior parameters
        params["vpnconn_peer_type_%s_%s" % (name, node1.name)] = peer1["type"].upper()
        if peer1["type"] == "ip":
            interface2 = node2.interfaces[
                node2.params[peer1.get("nic", "internet_nic")]
            ]
            params["vpnconn_peer_ip_%s_%s" % (name, node1.name)] = interface2.ip
            params["vpnconn_activation_%s_%s" % (name, node1.name)] = "ALWAYS"
        elif peer1["type"] == "dynip":
            interface2 = node2.interfaces[
                node2.params[peer1.get("nic", "internet_nic")]
            ]
            params["vpnconn_activation_%s_%s" % (name, node1.name)] = "PASSIVE"
        else:
            raise ValueError(
                "Invalid choice of left peer type '%s', must be one of"
                " 'ip', 'dynip'" % peer1["type"]
            )
        params["vpnconn_peer_type_%s_%s" % (name, node2.name)] = peer2["type"].upper()
        interface1 = node1.interfaces[node1.params[peer2.get("nic", "internet_nic")]]
        params["vpnconn_peer_ip_%s_%s" % (name, node2.name)] = interface1.ip
        params["vpnconn_activation_%s_%s" % (name, node2.name)] = "ALWAYS"

        # authentication parameters
        if auth is None:
            params["vpnconn_key_type_%s" % name] = "NONE"
        elif auth["type"] == "pubkey":
            params["vpnconn_key_type_%s" % name] = "PUBLIC"
        elif auth["type"] == "psk":
            params["vpnconn_key_type_%s" % name] = "PSK"

            psk = auth["psk"]
            left_id = auth["left_id"]
            left_id_type = "IP" if left_id == "" else "CUSTOM"
            right_id = auth["right_id"]
            right_id_type = "IP" if right_id == "" else "CUSTOM"

            params["vpnconn_psk_%s" % name] = psk
            params["vpnconn_psk_foreign_id_%s_%s" % (name, node1.name)] = right_id
            params["vpnconn_psk_foreign_id_type_%s_%s" % (name, node1.name)] = (
                right_id_type
            )
            params["vpnconn_psk_own_id_%s_%s" % (name, node1.name)] = left_id
            params["vpnconn_psk_own_id_type_%s_%s" % (name, node1.name)] = left_id_type
            params["vpnconn_psk_foreign_id_%s_%s" % (name, node2.name)] = left_id
            params["vpnconn_psk_foreign_id_type_%s_%s" % (name, node2.name)] = (
                left_id_type
            )
            params["vpnconn_psk_own_id_%s_%s" % (name, node2.name)] = right_id
            params["vpnconn_psk_own_id_type_%s_%s" % (name, node2.name)] = right_id_type
        else:
            raise ValueError(
                "Invalid choice of authentication type '%s', must be one of"
                " 'pubkey', 'psk', or 'none'" % auth["type"]
            )

        # overwrite the base vpn parameters with other already defined tunnel parameters
        params1 = params.object_params(node1.name)
        params2 = params.object_params(node2.name)
        params1.update(node1.params)
        params2.update(node2.params)
        node1.params.clear()
        node2.params.clear()
        node1.params.update(params1)
        node2.params.update(params2)

        self._params = params
        self._left = node1
        self._left_iface = interface1
        self._left_net = netconfig1
        self._right = node2
        self._right_iface = interface2
        self._right_net = netconfig2
        self._name = name

        logging.info("Produced tunnel from parameters is %s", self)

    def __repr__(self) -> str:
        """Provide a representation of the object."""
        left_net = "none" if self.left_net is None else self.left_net.net_ip
        right_net = "none" if self.right_net is None else self.right_net.net_ip
        tunnel_tuple = (
            self.name,
            self.left.name,
            self.left_iface.ip,
            self.right.name,
            self.right_iface.ip,
            left_net,
            right_net,
        )
        return (
            "[tunnel] name='%s', left='%s(%s)', right='%s(%s)', lnet='%s', rnet='%s'"
            % tunnel_tuple
        )

    def connects_nodes(self, node1: VMNode, node2: VMNode) -> bool:
        """
        Check whether a tunnel connects two vm nodes.

        The vm nodes can be connected directly as tunnel
        peers or indirectly in tunnel connected LANs (netconfigs).

        :param node1: one side vm of the tunnel
        :param node2: another side vm of the tunnel
        :returns: whether the tunnel connects the two nodes
        """

        def on_the_left(node: VMNode) -> bool:
            if node == self.left:
                logging.debug(
                    "The node %s is the left end point of the tunnel %s", node, self
                )
                return True
            if self.left_net is not None and node.check_interface(
                self.left_net.has_interface
            ):
                logging.debug(
                    "The node %s is in the left end site of the tunnel %s", node, self
                )
                return True
            if self.left_params["vpnconn_lan_type"] == "CUSTOM":
                if node.check_interface(self.left_net.can_add_interface):
                    logging.debug(
                        "The node %s is forwarded from the left end of the tunnel %s",
                        node,
                        self,
                    )
                    return True
            return False

        def on_the_right(node: VMNode) -> bool:
            if node == self.right:
                logging.debug(
                    "The node %s is the right end point of the tunnel %s", node, self
                )
                return True
            if self.right_net is not None and node.check_interface(
                self.right_net.has_interface
            ):
                logging.debug(
                    "The node %s is in the right end site of the tunnel %s", node, self
                )
                return True
            if self.right_params["vpnconn_lan_type"] == "CUSTOM":
                if node.check_interface(self.right_net.can_add_interface):
                    logging.debug(
                        "The node %s is forwarded from the right end of the tunnel %s",
                        node,
                        self,
                    )
                    return True
            return False

        logging.debug(
            "Checking if the tunnel %s connects %s and %s", self, node1, node2
        )
        if on_the_left(node1) and on_the_right(node2):
            return True
        elif on_the_right(node1) and on_the_left(node2):
            return True
        else:
            return False

    def _get_peer_variant(
        self,
        left_local: dict[str, str],
        left_remote: dict[str, str],
        left_peer: dict[str, str],
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        """
        Convert triple of parameters according to ipsec rules.

        Returns a triple of parameters for for the peer. Return
        default parameter where the left variant has used a more
        "exotic" value.
        """
        right_local = {"type": "nic"}
        right_remote = {"type": "custom"}
        right_peer = {"type": "ip"}

        if left_local["type"] == "nic":
            right_remote["type"] = "custom"
            right_remote["nic"] = left_local["nic"]
        elif left_local["type"] == "internetip":
            right_remote["type"] = "externalip"
        if left_remote["type"] == "custom":
            if left_local["type"] == "custom":
                right_local["type"] = "custom"
            else:
                right_local["type"] = "nic"
                right_local["nic"] = left_remote["nic"]
        elif left_remote["type"] == "externalip":
            right_local["type"] = "internetip"

        if left_peer["type"] == "dynip":
            right_peer["type"] = "ip"
            right_peer["nic"] = left_peer["nic"]
        # road warriors are always assumed to be on the left side
        elif left_peer["type"] == "ip":
            right_peer["type"] = "ip"
            right_peer["nic"] = left_peer["nic"]

        return right_local, right_remote, right_peer

    def configure_between_endpoints(
        self, apply_extra_options: dict[str, Any] = None
    ) -> None:
        """
        Build a tunnel between two endpoint vms.

        :param apply_extra_options: extra switches to apply as key exchange, firewall ruleset, etc.
        """
        logging.info(
            "Building a tunnel %s between %s and %s",
            self.name,
            self.left.name,
            self.right.name,
        )

        if self.left_params["vpnconn_key_type"] == "PUBLIC":
            self.import_key_params(self.left, self.right)
        if self.right_params["vpnconn_key_type"] == "PUBLIC":
            self.import_key_params(self.right, self.left)

        self.configure_on_endpoint(self.left, apply_extra_options)
        self.configure_on_endpoint(self.right, apply_extra_options)

    def configure_on_endpoint(
        self, node: VMNode, apply_extra_options: dict[str, Any] = None
    ) -> None:
        """
        Configure a tunnel on an end point virtual machine.

        :param node: node end point where the tunnel will be configured
        :param apply_extra_options: extra switches to apply as key exchange, firewall ruleset, etc.
        :raises: :py:class:`ValueError` if some of the supplied configuration is not valid

        The provided virtual machine parameters will be used
        for configuration of the tunnel.

        The tunnel name can be used to also reconfigure an existing tunnel.
        """
        if not apply_extra_options:
            apply_extra_options = {}

        vm = node.platform
        logging.info("Configuring tunnel %s on %s", self.name, node.name)
        if node == self.left:
            params1 = self.left_params
            params2 = self.right_params
            interface1, interface2 = self.left_iface, self.right_iface
            netconfig1, netconfig2 = self.left_net, self.right_net
        elif node == self.right:
            params1 = self.right_params
            params2 = self.left_params
            interface1, interface2 = self.right_iface, self.left_iface
            netconfig1, netconfig2 = self.right_net, self.left_net
        else:
            raise ValueError(
                "The configured %s is not among the tunnel end nodes %s and %s",
                node.name,
                self.left.name,
                self.right.name,
            )

        # if opposite end point is a road warrior (behind NAT)
        if params1["vpnconn_activation"] == "PASSIVE":
            nat_ip = interface2.netconfig.interfaces[interface2.netconfig.gateway].ip
            peer_ip2 = params1.get("vpnconn_nat_peer_ip", nat_ip)
        else:
            assert interface2.ip == params1["vpnconn_peer_ip"]
            peer_ip2 = params1["vpnconn_peer_ip"]

        add_cmd = "ip tunnel add %s mode gre remote %s local %s ttl 255"
        vm.session.cmd(add_cmd % (self.name, peer_ip2, interface1.ip))
        vm.session.cmd("ip link set %s up" % self.name)
        lan_iface = node.check_interface(netconfig1.has_interface)
        if lan_iface is None:
            raise ValueError(
                "Tunnel end node %s does not have interface in tunnel end net %s in %s"
                % (node.name, netconfig1.net_ip, self)
            )
        vm.session.cmd("ip addr add %s dev %s" % (lan_iface.ip, self.name))
        # roadwarrior connections don't have a remove netconfig
        if netconfig2 is not None:
            vm.session.cmd(
                "ip route add %s/%s dev %s"
                % (netconfig2.net_ip, netconfig2.mask_bit, self.name)
            )

        if apply_extra_options.get("apply_firewall_ruleset", True):
            # 47 stand for GRE (Generic Routing Encapsulation)
            protocol_id = apply_extra_options.get("tunnel_protocol_id", 47)
            # if current end point is a road warrior (behind NAT)
            if params2["vpnconn_activation"] == "PASSIVE":
                vm.session.cmd(
                    "iptables -I INPUT -i eth1 -p %s -j ACCEPT" % protocol_id
                )
            vm.session.cmd("iptables -I INPUT -i %s -p icmp -j ACCEPT" % self.name)
            vm.session.cmd("iptables -I OUTPUT -o %s -p icmp -j ACCEPT" % self.name)

    def import_key_params(self, from_node: VMNode, to_node: VMNode) -> None:
        """
        Generate own key configuration at the source vm and foreign key configuration at the destination vm.

        :param from_node: source node to get the key from (and generate own key
                          configuration on it containing all relevant key information)
        :param to_node: destination node to import the key to (and generate foreign key
                        configuration on it containing all relevant key information)
        """
        assert (
            from_node != to_node
        ), "Cannot import key parameters from a vm node to itself"
        if from_node not in [self.left, self.right]:
            raise ValueError(
                "The keys are not imported from any of the tunnel end points %s and %s and "
                "%s is not one of them"
                % (self.left.name, self.right.name, from_node.name)
            )
        if to_node not in [self.left, self.right]:
            raise ValueError(
                "The keys are not imported to any of the tunnel end points %s and %s and "
                "%s is not one of them"
                % (self.left.name, self.right.name, to_node.name)
            )
        from_vm, to_vm = from_node.platform, to_node.platform

        own_key_params = Params({"vpnconn_own_key_name": "sample-key"})
        from_vm.params.update(own_key_params)

        def get_imported_key_params(from_params: Params) -> Params:
            to_params = from_params.copy()
            to_params["vpnconn_foreign_key_name"] = from_params["vpnconn_own_key_name"]
            del to_params["vpnconn_own_key_name"]
            return to_params

        foreign_key_params = get_imported_key_params(own_key_params)
        to_vm.params.update(foreign_key_params)

        raise NotImplementedError(
            "Public key authentication is not implemented for any guest OS"
        )
