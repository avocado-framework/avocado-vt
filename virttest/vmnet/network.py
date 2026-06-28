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
Utility to manage local networks of vms and various topologies.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
The main class is the VMNetwork class and is used to perform all
network related configuration for each virt test (store all its
network information, offer all the network related services it
needs, etc.). It can be used to test Proxy, Port forwarding,
VPN, NAT, etc.

Each vm is a network node and can have one of few currently supported
operating systems. For ease of defaults use it is recommended to have
at least three nics, respectively with the role of host nic for local
isolated connection to the host, the role of internet nic for (internet)
connection to the other nodes, and the role of LAN nic for other any
other connections to vm's own LANs.

Ephemeral clients are based on RIP Linux and are temporary clients
created just for the duration of a test. An arbitrary number of those
can be spawned depending on test requirements and available resources.

INTERFACE
------------------------------------------------------

"""

import os
import re
import time
from typing import Any
import logging as log

import collections

from avocado.utils import process
from avocado.core import exceptions
from aexpect.client import RemoteSession
from virttest import utils_net
from virttest.utils_env import Env
from virttest.utils_params import Params
from virttest.qemu_vm import VM

from .interface import VMInterface
from .node import VMNode
from .netconfig import VMNetconfig
from .tunnel import VMTunnel

logging = log.getLogger("avocado.job." + __name__)


#: networking service backend paths
BIND_DHCP_CONFIG = "/etc/dhcp/dhcpd.conf"
BIND_DNS_CONFIG = "/etc/named.conf"
BIND_DECLARATIONS = "/var/named"
DNSMASQ_CONFIG = "/etc/dnsmasq.d/avocado.conf"
DNSMASQ_HOSTS = "/etc/avocado-hosts.conf"
DNSMASQ_PIDFILE = "/var/run/avocado-dnsmasq.pid"


class VMNetwork(object):
    """
    Any VMNetwork instance can be used to connect vms in various network topologies.

    It can also be used to reconfigure, ping, retrieve the session of, as well as spawn
    clients for each of them.
    """

    def __init__(self, params: Params, env: Env) -> None:
        """
        Construct a network data structure given the test parameters, the `env` and the `test` instance.

        .. note:: The params attribute is just a shallow copy to preserve the hierarchy:
            network level params = test level params -> node level params = test object params
            -> interface level params = rarely used outside of the vm network
        """
        self.params = params
        self.env = env

        # component types (could be replaced with extended ones)
        if getattr(self, "new_node", None) is None:
            self.new_node = VMNode
        if getattr(self, "new_interface", None) is None:
            self.new_interface = VMInterface
        if getattr(self, "new_netconfig", None) is None:
            self.new_netconfig = VMNetconfig
        if getattr(self, "new_tunnel", None) is None:
            self.new_tunnel = VMTunnel

        # component instances
        self.nodes = {}
        self.interfaces = {}
        self.netconfigs = {}
        self.tunnels = {}

        for vm_name in params.objects("vms"):

            # NOTE: since the vmnet can be used outside of a test, the existence
            # of the vm object is not guaranteed as well as the updated version
            # of its parameters
            vm = env.get_vm(vm_name)
            vm_params = params.object_params(vm_name)
            if vm is None:
                vm = env.create_vm(
                    params.get("vm_type"),
                    params.get("target"),
                    vm_name,
                    vm_params,
                    "/tmp",
                )
            else:
                vm.params = vm_params

            self.nodes[vm_name] = self.new_node(vm)
            self.integrate_node(self.nodes[vm_name])
        logging.debug("Constructed network configuration:\n%s", self)

    def __repr__(self) -> str:
        """Provide a representation of the object."""
        dump = "[vmnet] netconfigs='%s'" % len(self.netconfigs.keys())
        for netconfig in self.netconfigs.values():
            dump = "%s\n\t%s" % (dump, str(netconfig))
            for iface in netconfig.interfaces.values():
                dump = "%s\n\t\t%s -> %s" % (dump, str(iface), str(iface.node))
        return dump

    def start_all_sessions(self) -> None:
        """Start a session to each of the vm nodes."""
        for node in self.nodes.values():
            node.get_session()

    """VM node retrieval methods"""

    def _get_single_node(self) -> VMNode:
        """Get the only vm node in the network and raise error if it is not the only one."""
        if len(self.nodes.values()) != 1:
            raise exceptions.TestError(
                "A multi-vm network was thought of as a single-vm network"
            )
        else:
            return list(self.nodes.values())[0]

    def get_single_vm(self) -> VM:
        """
        Get the only vm in the network.

        :returns: only vm in the network
        """
        node = self._get_single_node()
        return node.platform

    def get_single_vm_with_session(self) -> tuple[VM, RemoteSession]:
        """
        Get the only vm in the network and its only session.

        :returns: vm and its last session
        """
        node = self._get_single_node()
        if node.last_session is None:
            self.start_all_sessions()
        return (node.platform, node.last_session)

    def get_single_vm_with_session_and_params(self) -> tuple[VM, RemoteSession, Params]:
        """
        Get the only vm in the network and its only session as well as configuration (to replace the test configuration).

        :returns: vm, its last session, and its params
        """
        node = self._get_single_node()
        if node.last_session is None:
            self.start_all_sessions()
        return (node.platform, node.last_session, node.params)

    def get_ordered_vms(self, vm_num: int = None) -> tuple[VM, ...]:
        """
        Get all N (``=vm_num``) vms in the network ordered by their name.

        :param vm_num: number N of vms
        :returns: ordered vms
        :raises: :py:class:`exceptions.TestError` if # of vms != N
        """
        if vm_num is not None and len(self.nodes.values()) != vm_num:
            raise exceptions.TestError(
                "The vm network was expected to have %s vms while "
                "it has %s" % (vm_num, len(self.nodes.values()))
            )
        else:
            vms = []
            for key in sorted(self.nodes.keys()):
                vms.append(self.nodes[key].platform)
            return tuple(vms)

    def get_vms(self) -> Any:
        """
        Get a named tuple of vms in the network with their parametrically defined roles.

        :returns: tuple t with t.client = <vm1 object> and t.server = <vm2 object>
        :raises: :py:class:`exceptions.TestError` if some roles don't have assigned vms

        This is the main and most recommended vm retrieval method.

        Example Cartesian configuration::

            roles = "client server"
            client = "vm1"
            server = "vm2"
        """
        roles = {}
        for role in self.params.objects("roles"):
            roles[role] = self.params.get(role)
            if roles[role] is None:
                raise exceptions.TestError("No vm assigned to the role %s" % role)
        logging.debug("Roles for vms: %s", roles)

        # NOTE: fix the keys order to a particular order
        role_keys = roles.keys()
        role_tuple = collections.namedtuple("role_tuple", role_keys)
        role_platforms = [self.nodes[roles[key]].platform for key in role_keys]
        return role_tuple(*role_platforms)

    """VM network modification methods"""

    def integrate_node(self, node: VMNode) -> None:
        """
        Add all interfaces and netconfigs resulting from a new vm node into the vm network.

        Thus integrate the configuration into the available one.

        :param node: vm node to be integrated into the network
        """
        logging.debug("Generating all interfaces for %s", node.name)
        if node in self.nodes:
            raise AssertionError("The vm node has already been integrated")
        if len(node.interfaces) > 0:
            raise AssertionError(
                "The integrated vm node must not have any initialized interfaces"
            )

        for nic_name in node.platform.params.objects("nics"):
            ikey = "%s.%s" % (node.name, nic_name)

            nic_params = node.platform.params.object_params(nic_name)
            new_interface = self.new_interface(nic_name, nic_params)

            node.interfaces[nic_name] = new_interface
            self.interfaces[ikey] = new_interface
            self.interfaces[ikey].node = node

            logging.debug(
                "Generated interface {0}: {1}".format(ikey, self.interfaces[ikey])
            )

        for interface in node.interfaces.values():
            logging.debug(
                "Checking required netconfig for interface {0}".format(interface)
            )
            for netconfig in self.netconfigs.values():
                if netconfig.can_add_interface(interface):
                    logging.debug(
                        "Adding interface {0} to previous {1}".format(
                            interface, netconfig
                        )
                    )
                    netconfig.add_interface(interface)
                    break
            else:
                netconfig = self.new_netconfig()
                netconfig.from_interface(interface)
                logging.debug(
                    "Adding interface {0} to a new {1}".format(interface, netconfig)
                )
                netconfig.add_interface(interface)
                self.netconfigs[netconfig.net_ip] = netconfig

    def reattach_interface(
        self,
        client: VM,
        server: VM,
        client_nic: str = "internet_nic",
        server_nic: str = "lan_nic",
        proxy_nic: str = "",
    ) -> None:
        """
        Reconfigure a network interface of a vm reattaching it to a different interface's network config.

        :param client: vm whose interace will be rattached
        :param server: vm whose network will the interface be attached to
        :param client_nic: role of the nic of the client
        :param server_nic: role of the nic of the server
        :param proxy_nic: name of a proxyARP nic of the server

        If the `proxy_nic` is defined and the second interface (`server_nic`) is
        different than the `proxy_nic` value, it is assumed to be and turned
        into a proxyarp interface whose responses are provided by the actual
        interface defined in the `proxy_nic` parameter.

        Any processing related to the vm or the netconfig's servers
        must be performed separately.

        A typical processing for the clients is to insert a DHCP/DNS
        host, while a typical processing for the vm is to recreate it
        on top of the moved bridges with or without session.

        A typical processing for the vm is to reconfigure the nic type of
        `server_nic` to PROXYARP and its IP to the IP of `proxy_nic`.
        """
        client_nic = self.nodes[client.name].params[client_nic]
        server_nic = self.nodes[server.name].params[server_nic]
        interface = self.interfaces["%s.%s" % (client.name, client_nic)]
        ref_interface = self.interfaces["%s.%s" % (server.name, server_nic)]
        proxy_interface = None
        if proxy_nic != "" and proxy_nic != server_nic:
            proxy_interface = self.interfaces["%s.%s" % (server.name, proxy_nic)]
        netconfig = ref_interface.netconfig
        logging.debug("Reattaching %s to %s", interface, netconfig)

        # detach from the current network
        del interface.netconfig.interfaces[interface.ip]
        # attach to the new network - with validation and proper attribute update
        interface.ip = netconfig.get_allocatable_address()
        netconfig.add_interface(interface)
        if proxy_interface is not None:
            # TODO: this invalidates the network config of the ref_interface
            # and if used often enough it has to be improved
            del netconfig.interfaces[interface.ip]
            ref_interface.ip = proxy_interface.ip
            interface.ip = proxy_interface.netconfig.get_allocatable_address()
            interface.netconfig = proxy_interface.netconfig

        # TODO: need to update all relevant parameters or regenerate at once
        self.params["netdst_%s_%s" % (client_nic, client.name)] = netconfig.netdst
        self.params["ip_%s_%s" % (client_nic, client.name)] = interface.ip
        self.params["netmask_%s_%s" % (client_nic, client.name)] = netconfig.netmask
        logging.debug("Reattached interface is now %s", interface)

    """VM network host action methods"""

    def _configure_local_dhcp(
        self, config_string: str, declarations: dict[str, str], interface: VMInterface
    ) -> str:
        if interface.netconfig is None:
            raise exceptions.TestError(
                "The interface %s does not belong to any netconfig", interface
            )
        elif interface.node is None:
            raise exceptions.TestError(
                "The interface %s does come from any vm node", interface
            )
        elif interface.netconfig.netdst in self.params.get("host_dhcp_blacklist", ""):
            raise exceptions.TestError(
                "The netconfig %s is blacklisted for host DHCP service!"
                % interface.netconfig
            )
        else:
            netconfig = interface.netconfig
            node = interface.node

        # main DHCP config
        if interface.params.get("host_dhcp_authoritative", "no") == "yes":
            if not re.search(
                "netconfig %s netmask %s {.+?}" % (netconfig.net_ip, netconfig.netmask),
                config_string,
                re.DOTALL,
            ):
                logging.info("Adding DHCP netconfig %s", netconfig.net_ip)
                netconfig_string = declarations["subnet"]
                netconfig_string = netconfig_string.replace("#IP#", netconfig.net_ip)
                netconfig_string = netconfig_string.replace(
                    "#NETMASK#", netconfig.netmask
                )
                netconfig_string = netconfig_string.replace(
                    "#RANGE_START#", netconfig.ip_start
                )
                netconfig_string = netconfig_string.replace(
                    "#RANGE_STOP#", netconfig.ip_end
                )
                netconfig_string = netconfig_string.replace(
                    "#DNSSERVERS#", netconfig.host_ip
                )
                netconfig_string = netconfig_string.replace(
                    "#ROUTERS#", netconfig.host_ip
                )
                logging.debug("Adding netconfig to dhcpd.conf:\n%s", netconfig_string)
                config_string += "\n" + netconfig_string
        else:
            if not re.search(
                "dhcp-range=%s" % netconfig.netdst, config_string, re.DOTALL
            ):
                logging.info("Adding DHCP netconfig %s", netconfig.net_ip)
                netconfig_string = "dhcp-range=%s,%s,%s,%s" % (
                    netconfig.netdst,
                    netconfig.ip_start,
                    netconfig.ip_end,
                    netconfig.netmask,
                )
                logging.debug("Adding netconfig to dnsmasc.conf:\n%s", netconfig_string)
                config_string += "\n" + netconfig_string

        # register DHCP host in the DHCP config file
        if interface.params.get("host_dhcp_authoritative", "no") == "yes":
            if not re.search("host %s {.+?}" % node.name, config_string, re.DOTALL):
                logging.info("Adding DHCP host %s", node.name)
                host_string = declarations["host"]
                host_string = host_string.replace("#VMNAME#", node.name)
                host_string = host_string.replace(
                    "#VMHOSTNAME#", "%s.net.lan" % node.name
                )
                host_string = host_string.replace("#INIC_MAC#", interface.mac)
                host_string = host_string.replace("#INIC_IP#", interface.ip)
                logging.debug("Adding host to dhcpd.conf:\n%s", host_string)
                config_string += "\n" + host_string
        else:
            logging.info("Adding DHCP host %s", node.name)
            host_string = "dhcp-host=%s,%s" % (interface.mac, interface.ip)
            logging.debug("Adding host to dnsmasc.conf:\n%s", host_string)
            config_string += "\n" + host_string
            # handle cases with non-authoritative DHCP only
            if (
                interface.params.get("host_dns_service", "no") == "no"
                or interface.params.get("host_dns_authoritative", "no") == "yes"
            ):
                # TODO: currently DNSMASQ does not support DHCP only mode for a subset of interfaces
                # (setting the port to 0 is the way to do it but this will disable DNS for all)
                # config_string += "\nport=0"
                config_string += "\ninterface=%s" % netconfig.netdst

        return config_string

    def _configure_local_dns(
        self, config_string: str, declarations: dict[str, str], interface: VMInterface
    ) -> str:
        if interface.netconfig is None:
            raise exceptions.TestError(
                "The interface %s does not belong to any netconfig", interface
            )
        elif interface.node is None:
            raise exceptions.TestError(
                "The interface %s does come from any vm node", interface
            )
        elif interface.netconfig.netdst in self.params.get("host_dns_blacklist", ""):
            raise exceptions.TestError(
                "The netconfig %s is blacklisted for host DNS service!"
                % interface.netconfig
            )
        else:
            netconfig = interface.netconfig
            node = interface.node

        if interface.params.get("host_dns_authoritative", "no") == "yes":
            if not re.search('view "%s"' % netconfig.view, config_string, re.DOTALL):

                # main DNS config
                dns_listen = re.search(
                    "listen-on port 53 {.*?}", config_string
                ).group()[:-1]
                if netconfig.host_ip not in dns_listen:
                    config_string = config_string.replace(
                        dns_listen, "%s %s;" % (dns_listen, netconfig.host_ip)
                    )
                dns_forwarders = re.search("forwarders {.*?}", config_string).group()[
                    :-1
                ]
                if netconfig.forwarder not in dns_forwarders:
                    config_string = config_string.replace(
                        dns_forwarders, "%s %s;" % (dns_forwarders, netconfig.forwarder)
                    )

                # prepare the view
                logging.info("Adding DNS view for %s", netconfig.net_ip)
                view_string = declarations["view"]
                view_string = view_string.replace("#VIEWNAME#", netconfig.view)
                view_string = view_string.replace("#IP#", netconfig.net_ip)
                view_string = view_string.replace("#MASKBIT#", netconfig.mask_bit)
                view_string = view_string.replace("#ZONENAME#", netconfig.domain)
                view_string = view_string.replace("#ZONEREV#", netconfig.rev)
                view_string = view_string.replace("#ZONEFILE#", netconfig.view)
                logging.debug("Adding DNS view to named.conf:\n%s", view_string)
                config_string += view_string

                # DNS zone files
                fwd_string = declarations["fwd"].replace("#ZONENAME#", netconfig.domain)
                fwd_string = fwd_string.replace("#ZONEIP#", netconfig.host_ip)
                rev_string = declarations["rev"].replace("#ZONENAME#", netconfig.domain)
                rev_string = rev_string.replace("#ZONEREV#", netconfig.rev)
                fwd_string += "%s \t\t IN \t A \t %s\n" % (node.name, interface.ip)
                with open(
                    os.path.join(BIND_DECLARATIONS, "%s.fwd" % netconfig.view), "w"
                ) as f:
                    f.write(fwd_string)
                with open(
                    os.path.join(BIND_DECLARATIONS, "%s.rev" % netconfig.view), "w"
                ) as f:
                    f.write(rev_string)

        else:
            if not re.search(
                "interface=%s" % netconfig.netdst, config_string, re.DOTALL
            ):

                # main DNS config
                logging.info("Adding DNS view for %s", netconfig.net_ip)
                view_string = "\n" + "interface=%s\n" % netconfig.netdst
                view_string += "domain=%s,%s/%s\n" % (
                    netconfig.domain,
                    netconfig.net_ip,
                    netconfig.mask_bit,
                )
                local_string = "local=/%s/\n" % netconfig.domain
                if local_string not in config_string:
                    view_string += local_string
                logging.debug("Adding DNS view to dnsmasc.conf:\n%s", view_string)
                config_string += view_string

                # prepare the hosts
                host_string = "%s %s\n" % (netconfig.host_ip, netconfig.domain)
                if host_string not in declarations["hosts"]:
                    declarations["hosts"] += host_string
                guest_host_string = "%s %s\n" % (interface.ip, node.name)
                declarations["hosts"] += guest_host_string

                # handle cases with non-authoritative DNS only
                if (
                    interface.params.get("host_dhcp_service", "no") == "no"
                    or interface.params.get("host_dhcp_authoritative", "no") == "yes"
                ):
                    config_string.replace(
                        "interface=%s" % netconfig.netdst,
                        "no-dhcp-interface=%s" % netconfig.netdst,
                    )

        return config_string

    def _configure_local_nat(
        self, interface: VMInterface, set_rules: bool = True
    ) -> None:
        if interface.netconfig is None:
            raise exceptions.TestError(
                "The interface %s does not belong to any netconfig", interface
            )
        elif interface.node is None:
            raise exceptions.TestError(
                "The interface %s does come from any vm node", interface
            )
        elif interface.netconfig.netdst in self.params.get("host_dns_blacklist", ""):
            raise exceptions.TestError(
                "The netconfig %s is blacklisted for host DNS service!"
                % interface.netconfig
            )
        else:
            netconfig = interface.netconfig

        internal_netdst = netconfig.netdst
        external_netdst = netconfig.ext_netdst
        rev_ops = "-i %s -o %s -m state" % (external_netdst, internal_netdst)
        post_ops = "-s %s/%s ! -d %s/%s -o %s" % (
            netconfig.net_ip,
            netconfig.mask_bit,
            netconfig.net_ip,
            netconfig.mask_bit,
            external_netdst,
        )

        process.run(
            "iptables -D FORWARD %s --state RELATED,ESTABLISHED -j ACCEPT" % rev_ops,
            ignore_status=True,
        )
        process.run(
            "iptables -t nat -D POSTROUTING %s -j MASQUERADE" % post_ops,
            ignore_status=True,
        )

        if set_rules:
            logging.info(
                "Adding NAT routing to the netconfig (postrouting to %s)",
                external_netdst,
            )
            process.run(
                "iptables -I FORWARD %s --state RELATED,ESTABLISHED -j ACCEPT" % rev_ops
            )
            process.run("iptables -t nat -I POSTROUTING %s -j MASQUERADE" % post_ops)

    def setup_host_services(self) -> None:
        """Provide all necessary services like DHCP, DNS and NAT to restrict all tests locally."""
        logging.info("Checking for local DHCP, DNS and NAT service requirements")
        dhcp_declarations = {}
        dns_declarations = {}
        dns_set_config = False
        dhcp_set_config = False
        dns_dhcp_set_config = False

        # load templates
        data_path = os.path.join(os.path.dirname(__file__), "templates")
        with open(os.path.join(data_path, "dhcpd.conf.template"), "r") as f:
            dhcp_string = f.read()
            dhcp_declarations["subnet"] = re.search(
                "subnet #IP# netmask #NETMASK#+ {.+?}", dhcp_string, re.DOTALL
            ).group()
            dhcp_declarations["host"] = re.search(
                "host #VMNAME# {.+?}", dhcp_string, re.DOTALL
            ).group()
            # load the config strings without the declarations
            dhcp_string = dhcp_string.replace("%s\n" % dhcp_declarations["subnet"], "")
            dhcp_string = dhcp_string.replace("%s\n" % dhcp_declarations["host"], "")
        with open(os.path.join(data_path, "named.conf.template"), "r") as f:
            dns_string = f.read()
        with open(os.path.join(data_path, "all.fwd.template"), "r") as f:
            dns_declarations["all"] = f.read()
        with open(os.path.join(data_path, "zone.fwd.template"), "r") as f:
            dns_declarations["fwd"] = f.read()
        with open(os.path.join(data_path, "zone.rev.template"), "r") as f:
            dns_declarations["rev"] = f.read()
        dns_declarations["view"] = re.search(
            'view "#VIEWNAME#" .+?rev";.+?};.+?};', dns_string, re.DOTALL
        ).group()
        # load the config strings without the declarations
        dns_string = dns_string.replace("%s\n" % dns_declarations["view"], "")
        with open(os.path.join(data_path, "dnsmasq.conf.template"), "r") as f:
            dns_dhcp_string = f.read()
        with open(os.path.join(data_path, "hosts.conf.template"), "r") as f:
            dns_declarations["hosts"] = f.read()

        # configure selected interfaces
        for interface in self.interfaces.values():
            # if the internet provider of the vm coincides with the host of the vm (for the current nic)
            if interface.params.get(
                "ip_provider", "no-provider"
            ) == interface.params.get("host", "no-host"):
                netconfig = interface.netconfig
                dhcp_ops = "-i %s" % (netconfig.netdst)
                dns_ops = "-i %s -d %s" % (netconfig.netdst, netconfig.host_ip)
                fwd_ops = "-s %s/%s -i %s" % (
                    netconfig.net_ip,
                    netconfig.mask_bit,
                    netconfig.netdst,
                )

                process.run(
                    "iptables -D INPUT %s -p udp -m udp --dport 67:68 -j ACCEPT"
                    % dhcp_ops,
                    ignore_status=True,
                )
                process.run(
                    "iptables -D FORWARD %s -j ACCEPT" % fwd_ops, ignore_status=True
                )
                if (
                    interface.params.get(
                        "host_dhcp_service", interface.params.get("host_services", "no")
                    )
                    == "yes"
                ):
                    process.run(
                        "iptables -I INPUT %s -p udp -m udp --dport 67:68 -j ACCEPT"
                        % dhcp_ops
                    )
                    process.run("iptables -I FORWARD %s -j ACCEPT" % fwd_ops)
                    if interface.params.get("host_dhcp_authoritative", "no") == "yes":
                        dhcp_string = self._configure_local_dhcp(
                            dhcp_string, dhcp_declarations, interface
                        )
                        dhcp_set_config = True
                    else:
                        dns_dhcp_string = self._configure_local_dhcp(
                            dns_dhcp_string, dhcp_declarations, interface
                        )
                        dns_dhcp_set_config = True

                process.run(
                    "iptables -D INPUT %s -p tcp -m tcp --dport 53 -j ACCEPT" % dns_ops,
                    ignore_status=True,
                )
                process.run(
                    "iptables -D INPUT %s -p udp -m udp --dport 53 -j ACCEPT" % dns_ops,
                    ignore_status=True,
                )
                if (
                    interface.params.get(
                        "host_dns_service", interface.params.get("host_services", "no")
                    )
                    == "yes"
                ):
                    process.run(
                        "iptables -I INPUT %s -p tcp -m tcp --dport 53 -j ACCEPT"
                        % dns_ops
                    )
                    process.run(
                        "iptables -I INPUT %s -p udp -m udp --dport 53 -j ACCEPT"
                        % dns_ops
                    )
                    if interface.params.get("host_dns_authoritative", "no") == "yes":
                        dns_string = self._configure_local_dns(
                            dns_string, dns_declarations, interface
                        )
                        dns_set_config = True
                    else:
                        dns_dhcp_string = self._configure_local_dns(
                            dns_dhcp_string, dns_declarations, interface
                        )
                        dns_dhcp_set_config = True

                # turn the host into NAT router for the netconfig
                self._configure_local_nat(
                    interface,
                    set_rules=interface.params.get(
                        "host_nat_service", interface.params.get("host_services", "no")
                    )
                    == "yes",
                )

                # ports for additional (custom) services
                for port in interface.params.objects("host_additional_ports"):
                    process.run(
                        "iptables -D INPUT -i %s -p tcp --dport %s -j ACCEPT"
                        % (netconfig.netdst, port),
                        ignore_status=True,
                    )
                    process.run(
                        "iptables -I INPUT -i %s -p tcp --dport %s -j ACCEPT"
                        % (netconfig.netdst, port)
                    )

            elif interface.params.get("ip_provider", "no-provider") == interface.ip:
                self_ops = "-i %s -o %s" % (
                    interface.netconfig.netdst,
                    interface.netconfig.netdst,
                )
                process.run(
                    "iptables -D FORWARD %s -j ACCEPT" % self_ops, ignore_status=True
                )
                process.run("iptables -I FORWARD %s -j ACCEPT" % self_ops)

        # write configurations if any
        if dhcp_set_config:
            logging.debug("Writing new DHCP config file:\n%s", dhcp_string)
            dhcp_config = BIND_DHCP_CONFIG
            if not os.path.exists("%s.bak" % dhcp_config):
                os.rename(dhcp_config, "%s.bak" % dhcp_config)
            with open(dhcp_config, "w") as f:
                f.write(dhcp_string)
            logging.debug("Resetting DHCP service")
            process.run("systemctl restart dhcpd.service")  # , ignore_status = True)
        else:
            process.run("systemctl stop dhcpd.service", ignore_status=True)
        if dns_set_config:
            logging.debug("Writing new DNS config file:\n%s", dns_string)
            dns_config = BIND_DNS_CONFIG
            if not os.path.exists("%s.bak" % dns_config):
                os.rename(dns_config, "%s.bak" % dns_config)
            with open(dns_config, "w") as f:
                f.write(dns_string)
            with open(os.path.join(BIND_DECLARATIONS, "all.fwd"), "w") as f:
                f.write(dns_declarations["all"])
            logging.debug("Resetting DNS service")
            process.run("systemctl restart named.service")
        else:
            process.run("systemctl stop named.service", ignore_status=True)
        if dns_dhcp_set_config:
            logging.debug("Writing new DHCP/DNS config file:\n%s", dns_dhcp_string)
            dns_dhcp_config = DNSMASQ_CONFIG
            with open(dns_dhcp_config, "w") as f:
                f.write(dns_dhcp_string)
            logging.debug(
                "Writing new DHCP/DNS hosts file:\n%s", dns_declarations["hosts"]
            )
            with open(DNSMASQ_HOSTS, "w") as f:
                f.write(dns_declarations["hosts"])
            logging.debug("Resetting DHCP/DNS service")
        if os.path.exists(DNSMASQ_PIDFILE):
            with open(DNSMASQ_PIDFILE) as f:
                try:
                    os.kill(int(f.read()), 15)
                except ProcessLookupError:
                    logging.debug("DNSMASQ process is already dead and can't be reset")
        if dns_dhcp_set_config:
            time.sleep(1)
            process.run("dnsmasq --conf-file=%s" % dns_dhcp_config)

    def _add_new_bridge(self, interface: VMInterface) -> None:
        netdst = interface.netconfig.netdst
        host_ip = interface.netconfig.host_ip
        mask_bit = interface.netconfig.mask_bit
        host_mac = interface.mac.replace("02:00", "02:20")

        def _debug_bridge_ip(netdst: str) -> None:
            output = process.run("ip addr show %s" % netdst, shell=True)
            logging.debug("ip addr output for %s:\n%s" % (netdst, output))

        logging.info("Adding bridge %s", netdst)
        # TODO: no original avocado-vt method could in utils_net like the ones from
        # the bridge manager could do this for us at least from the research at the time
        process.run("brctl addbr %s" % netdst)
        if interface.params.get("host", "") != "":
            logging.debug(
                "Adding this host with ip %s to %s and bringing it up", host_ip, netdst
            )
            # give a little more time for the new bridge before adding an interface for it
            time.sleep(1)
            # TODO: no original avocado-vt method in utils_net like set_ip() and
            # set_netmask() could do this for us at least from the research at the time
            process.run("ip addr add %s/%s dev %s" % (host_ip, mask_bit, netdst))
            process.run("ip link set %s address %s" % (netdst, host_mac))
            process.run("ip link set %s up" % netdst)
            # DEBUG only: See if setting the IP address worked
            _debug_bridge_ip(netdst)
        else:
            logging.debug("Bringing up interface of the bridge %s", netdst)
            utils_net.bring_up_ifname(netdst)
            _debug_bridge_ip(netdst)

    def _cleanup_bridge_interfaces(self, netdst: str) -> None:
        logging.debug("Resetting the bridge %s to remove unwanted interfaces", netdst)
        bridge_manager = utils_net.find_bridge_manager(netdst)
        bridges = bridge_manager.get_structure()
        logging.debug("Parsed bridge structure: %s", bridges)
        if netdst in bridges.keys():
            interfaces = bridges[netdst]["iface"]
            for ifname in interfaces:
                # BUG: a bug in avocado-vt forces us to use a direct method from the bridge manager instead
                # of the more elegant "utils_net.del_from_bridge(ifname, netdst)" which also fits better
                # our other calls - at least we managed to isolate the buggy and unimplemented interface calls
                bridge_manager.del_port(netdst, ifname)

    def setup_host_bridges(self) -> None:
        """
        Set up bridges and interfaces needed to create and isolate the network.

        The final network topology is derived entirely from the test parameters.
        """
        logging.info("Checking for any bridge requirements")
        boarding = []

        # iterate through the bridges that need our setup
        for key, interface in self.interfaces.items():
            vm_name, nic_name = key.split(".")
            if (
                interface.params.get("host_set_bridge", "yes") == "no"
                or interface.params.get("permanent_netdst", "yes") == "yes"
            ):
                continue

            # get any previous configuration if available - unfortunately,
            # no better way of handling missing key was available
            try:
                nic = interface.node.platform.virtnet[nic_name]
            except IndexError:
                logging.debug("No nic object %s is available at %s", nic_name, vm_name)
                nic = None

            # discover and setup the nic bridge if necessary
            if nic is None:
                new_netdst = interface.netconfig.netdst
            elif nic.netdst != interface.netconfig.netdst:
                logging.debug(
                    "The retrieved nic %s has old configuration - "
                    "falling back to the available interface %s",
                    nic_name,
                    interface,
                )
                new_netdst = interface.netconfig.netdst
            else:
                new_netdst = nic.netdst
            # if the netdst was reset and already boarding interfaces skip this
            if new_netdst not in boarding:
                logging.debug(
                    "Updating the bridge %s of the network card %s of %s",
                    new_netdst,
                    nic_name,
                    vm_name,
                )
                bridge_manager = utils_net.find_bridge_manager(new_netdst)
                # no manager for the current bridge is equivalent to the fact that it doesn't exist
                if bridge_manager is not None:
                    self._cleanup_bridge_interfaces(new_netdst)
                else:
                    self._add_new_bridge(interface)
                boarding.append(new_netdst)

            # discover and setup the nic interface on top of the nic bridge
            if nic is not None:
                new_ifname = nic.ifname
            else:
                new_ifname = None
            # if the interface is up and in particular if it exists before the upcoming test
            if new_ifname in utils_net.get_net_if():
                logging.debug(
                    "Adding back interface %s to bridge %s", new_ifname, new_netdst
                )
                utils_net.change_iface_bridge(new_ifname, new_netdst)
            else:
                logging.debug("Interface will be added to bridge during vm creation")

    """VM network guest action methods"""

    def spawn_clients(
        self, server_name: str, clients_num: int, nic: str = "lan_nic"
    ) -> tuple[VM, ...]:
        """
        Create and boot ephemeral clients for a given server.

        :param server_name: name of the vm that plays the role of a server
        :param clients_num: number of ephemeral clients to spawn
        :param nic: name of the nic of the server
        :returns: generated ephemeral clients
        """
        server = self.nodes[server_name].platform
        inherited_server_params = server.params.copy()
        logging.info("Spawning %i client(s) for %s", clients_num, server.name)
        new_client_params = self._generate_clients_parameters(
            server_name, clients_num, nic
        )
        # TODO: need to update all relevant parameters or regenerate at once
        self.params.update(new_client_params)
        inherited_server_params.update(new_client_params)
        new_clients = new_client_params["vms_%s" % server.name].strip().split(" ")
        for client_name in new_clients:
            self.params["vms"] += " %s" % client_name

            logging.debug("Registering the ephemeral vm in the environment")
            client_params = inherited_server_params.object_params(client_name)
            client = self.env.create_vm(
                client_params.get("vm_type"),
                client_params.get("target"),
                client_name,
                client_params,
                "/tmp",
            )

            logging.debug("Integrating the ephemeral vm in the vm network")
            self.nodes[client_name] = self.new_node(client, ephemeral=True)
            self.integrate_node(self.nodes[client_name])

            logging.debug("Adding as an intraclient and booting the ephemeral vm")
            interface = self.nodes[client_name].interfaces[client_params["nics"]]
            self._register_client_at_server(interface, server, enable_dhcp=True)
            self.nodes[client_name].platform.create()

        # verify clients are running (2nd loop so clients boot in parallel)
        for client_name in new_clients:
            self.nodes[client_name].get_session(serial=True)

        # NOTE: since such clients are created on the run and don't have nics for communication
        # with the host we need to disable some automatic postprocessing functionality
        self.params["kill_unresponsive_vms"] = "no"
        return tuple([self.nodes[key].platform for key in new_clients])

    def _generate_clients_parameters(
        self, server_name: str, clients_num: int, nic: str
    ) -> dict[str, str]:
        nic = self.nodes[server_name].params[nic]
        server_interface = self.nodes[server_name].interfaces[nic]
        mac_sections = server_interface.mac.split(":")
        server_netconfig = server_interface.netconfig

        overwrite_dict = {}
        overwrite_dict["vms_%s" % server_name] = ""

        for i in range(1, clients_num + 1):
            logging.debug("Adding client %i for %s", i, server_name)

            # main
            client = "%seph%i" % (server_name, i)
            overwrite_dict["vms_%s" % server_name] += "%s " % client
            overwrite_dict["start_vm_%s" % client] = "yes"
            overwrite_dict["kill_vm_%s" % client] = self.params.get(
                "kill_clients", "yes"
            )
            overwrite_dict["mem_%s" % client] = "512"
            overwrite_dict["images_%s" % client] = ""
            overwrite_dict["boot_order_%s" % client] = "dcn"
            overwrite_dict["cdroms_%s" % client] = "cd_rip"
            overwrite_dict["shell_prompt_%s" % client] = r"^[\#\$]"
            overwrite_dict["isa_serials_%s" % client] = "serial1"

            # network adapters
            client_nic = "%snic" % client
            overwrite_dict["nics_%s" % client] = client_nic
            overwrite_dict["nic_model_%s" % client] = "e1000"

            # unique mac generation
            new_section = str(i)
            if len(new_section) < 2:
                new_section = "0" + new_section
            client_mac = ":".join(mac_sections[:3] + [new_section] + mac_sections[-2:])
            overwrite_dict["mac_%s" % client_nic] = client_mac

            # networking configuration
            client_netconfig = server_netconfig
            client_ip = client_netconfig.get_allocatable_address()
            overwrite_dict["ip_%s" % client_nic] = client_ip
            overwrite_dict["netmask_%s" % client_nic] = client_netconfig.netmask
            overwrite_dict["netdst_%s" % client_nic] = client_netconfig.netdst

        return overwrite_dict

    def _register_client_at_server(
        self, interface: VMInterface, server: VM, enable_dhcp: bool = True
    ) -> None:
        """
        Register a client vm at a server vm.

        :param interface: network interface containing the new configuration
        :param server: server where the (DHCP) client will be registered
        :param enable_dhcp: whether to use DHCP or static IP
        """
        raise NotImplementedError("Need implementation for some OS")

    def _reconfigure_vm_nic(self, interface: VMInterface, vm: VM) -> None:
        """
        Reconfigure the NIC of a vm.

        :param interface: network interface containing the new configuration
        :param vm: vm whose nic will be reconfigured
        :raises: :py:class:`exceptions.TestError` if the client is an Android device
        :raises: :py:class:`exceptions.NotImplementedError` if the client is not compatible
        """
        logging.info("Reconfiguring the %s of %s", interface.name, vm.name)
        if vm.params["os_type"] == "windows":
            nic: str = interface.name
            network = self.params.get("nic_wname", nic) + " " + str(int(nic[1:]) + 1)
            # the first adapter number is omitted on windows
            network = network.rstrip(" 1")
            netcmd = 'netsh interface ip set address name="%s" source=static %s %s %s 0'
            vm.session.cmd(
                netcmd
                % (
                    network,
                    interface.ip,
                    interface.netconfig.netmask,
                    interface.netconfig.gateway,
                ),
                timeout=120,
            )
            netcmd = 'netsh interface ip add dns name="%s" addr=%s index=1'
            vm.session.cmd(netcmd % (network, interface.netconfig.gateway))
        elif vm.params["os_variant"] == "android":
            raise exceptions.TestError(
                "No static IP can be set for Android devices (%s)" % vm.name
            )
        else:
            raise NotImplementedError(
                "Trying to configure nic on %s with an unsupported os %s"
                % (vm.name, vm.params["os_variant"])
            )

    def change_network_address(
        self, netconfig: VMNetconfig, new_ip: str, new_mask: str = None
    ) -> None:
        """
        Change the ip of a netconfig.

        More specifically of the network interface of any vm participating in it.

        :param netconfig: netconfig to change the IP of
        :param new_ip: new IP address for the netconfig
        :param new_mask: new network mask for the netconfig

        .. note:: The network must have at least one interface in order to change its address.
        """
        logging.debug("Updating the network configuration of the vm network")
        for interface in list(netconfig.interfaces.values()):
            del netconfig.interfaces[interface.ip]
            interface.ip = netconfig.translate_address(interface.ip, new_ip)
            netconfig.interfaces[interface.ip] = interface

        assert len(netconfig.interfaces) > 0, (
            "The network %s must have at least one interface" % netconfig
        )
        nic_interface = list(netconfig.interfaces.values())[-1]
        nic_params = nic_interface.params.copy()
        nic_params["ip"] = new_ip
        nic_params["ip_provider"] = netconfig.translate_address(
            netconfig.gateway, new_ip
        )
        if new_mask is not None:
            nic_params["netmask"] = new_mask
        interface = self.new_interface(nic_interface.name, nic_params)

        del self.netconfigs[netconfig.net_ip]
        netconfig.from_interface(interface)
        netconfig.validate()
        self.netconfigs[netconfig.net_ip] = netconfig

        logging.debug("Updating the network configuration of the relevant platforms")
        for interface in netconfig.interfaces.values():
            node = interface.node
            logging.info("Changing the ip of %s to %s", node.name, interface.ip)

            self._reconfigure_vm_nic(interface, node.platform)

            # updating proto (higher level) params (test params -> vm params -> nic params)
            # TODO: need to update all relevant parameters or regenerate at once
            interface.params["netmask"] = new_mask
            interface.params["ip"] = interface.ip
            node.platform.params["ip_%s" % interface.name] = interface.ip
            node.platform.params["ip_%s_%s" % (interface.name, node.name)] = (
                interface.ip
            )

    def set_static_address(
        self,
        client: VM,
        server: VM,
        client_nic: str = "internet_nic",
        server_nic: str = "lan_nic",
    ) -> None:
        """
        Set a static IP address on a client vm.

        :param client: vm whose nic will get static IP
        :param server: vm whose network will provide a free static IP
        :param client_nic: role of the nic of the client
        :param server_nic: role of the nic of the server

        .. note:: This assumes running machines.
        """
        client.verify_alive()
        client_iface = self.interfaces[
            "%s.%s" % (client.name, self.nodes[client.name].params[client_nic])
        ]
        server_iface = self.interfaces[
            "%s.%s" % (server.name, self.nodes[server.name].params[server_nic])
        ]
        client_iface.netconfig.gateway = server_iface.ip
        self._reconfigure_vm_nic(client_iface, client)

    def configure_tunnel_between_vms(
        self,
        name: str,
        vm1: VM,
        vm2: VM,
        local1: dict[str, str] = None,
        remote1: dict[str, str] = None,
        peer1: dict[str, str] = None,
        auth: dict[str, str] = None,
        apply_extra_options: dict[str, Any] = None,
    ) -> None:
        """
        Configure a tunnel between two vms.

        :param name: name of the tunnel
        :param vm1: left side vm of the tunnel
        :param vm2: right side vm of the tunnel
        :param local1: left local type as in tunnel constructor
        :param remote1: left remote type as in tunnel constructor
        :param peer1: left peer type as in tunnel constructor
        :param auth: authentication configuration as described in the tunnel constructor
        :param apply_extra_options: extra switches to apply as key exchange, firewall ruleset, etc.
        """
        left_node = self.nodes[vm1.name]
        right_node = self.nodes[vm2.name]
        self.tunnels[name] = self.new_tunnel(
            name, left_node, right_node, local1, remote1, peer1, auth
        )
        self.tunnels[name].configure_between_endpoints(apply_extra_options)

    def configure_tunnel_on_vm(
        self, name: str, vm: VM, apply_extra_options: dict[str, Any] = None
    ) -> None:
        """
        Configure a tunnel on a vm, assuming it is manually or independently configured on the other end.

        :param name: name of the tunnel
        :param vm: vm where the tunnel will be configured
        :param apply_extra_options: extra switches to apply as key exchange, firewall ruleset, etc.
        :raises: :py:class:`exceptions.KeyError` if not all tunnel parameters are present

        Currently the method uses only existing tunnels.
        """
        if name not in self.tunnels:
            raise KeyError(
                "Currently, every tunnel has to be created defining both"
                " ends and it can only then be configured on a single vm %s" % vm.name
            )

        node = self.nodes[vm.name]
        self.tunnels[name].configure_on_endpoint(node, apply_extra_options)

    def configure_roadwarrior_vpn_on_server(
        self,
        name: str,
        server: VM,
        client: VM,
        local1: dict[str, str] = None,
        remote1: dict[str, str] = None,
        peer1: dict[str, str] = None,
        auth: dict[str, str] = None,
        apply_extra_options: dict[str, Any] = None,
    ) -> None:
        """
        Configure a VPN connection (tunnel) on a VM to act as a VPN server.

        This will allow individual clients to access it from the Internet

        Arguments are similar to the ones from :py:meth:`configure_tunnel_between_vms`
        with the exception of:

        :param server: vm which will be the VPN server for roadwarrior connections
        :param client: vm which will be connecting individual device

        Regarding the client, only its parameters will be updated by this method.
        """
        if local1 is None:
            local1 = {"type": "nic", "nic": "lan_nic"}
        if remote1 is None:
            remote1 = {"type": "modeconfig", "modeconfig_ip": "172.30.0.1"}
        if peer1 is None:
            peer1 = {"type": "dynip", "nic": "internet_nic"}
        if peer1["type"] != "dynip":
            raise exceptions.TestError(
                "Only dynamic IP peer type is possible for"
                "roadwarrior connections, not %s",
                peer1["type"],
            )

        left_node = self.nodes[server.name]
        right_node = self.nodes[client.name]
        self.tunnels[name] = self.new_tunnel(
            name, left_node, right_node, local1, remote1, peer1, auth
        )
        self.configure_tunnel_on_vm(name, server, apply_extra_options)

    def configure_vpn_route(
        self,
        vms: list[VM],
        vpns: list[str],
        remote1: dict[str, str] = None,
        peer1: dict[str, str] = None,
        auth: dict[str, str] = None,
        extra_apply_options: dict[str, Any] = None,
    ) -> None:
        """
        Build a set of VPN connections using VPN forwarding to gain access from one vm to another.

        Arguments are similar to the ones from :py:meth:`configure_tunnel_between_vms`
        with the exception of:

        :param vms: vms to participate in the VPN route
        :param vpns: VPNs over which the route will be constructed
        :raises: :py:class:`exceptions.TestError` if #vpns < #vms - 1 or #vpns < 2 or #vms < 2

        Infrastructure of point to point VPN connections must already exist.
        """
        if len(vpns) < 2 or len(vms) < 2 or len(vpns) < len(vms) - 1:
            raise exceptions.TestError(
                "Insufficient VPN infrastructure - unnecessary VPN forwarding"
            )

        logging.info("Building a VPN route %s", "-".join(vm.name for vm in vms))
        for i in range(len(vpns)):
            fvpn = "%sfwd" % vpns[i]
            if i == 0:
                prev_net = (
                    vms[i + 1].params.object_params(vpns[i]).get("vpnconn_remote_net")
                )
                prev_mask = (
                    vms[i + 1]
                    .params.object_params(vpns[i])
                    .get("vpnconn_remote_netmask")
                )
                next_net = (
                    vms[i + 1]
                    .params.object_params(vpns[i + 1])
                    .get("vpnconn_remote_net")
                )
                next_mask = (
                    vms[i + 1]
                    .params.object_params(vpns[i + 1])
                    .get("vpnconn_remote_netmask")
                )
            elif i == len(vpns) - 1:
                prev_net = (
                    vms[i].params.object_params(vpns[i - 1]).get("vpnconn_remote_net")
                )
                prev_mask = (
                    vms[i]
                    .params.object_params(vpns[i - 1])
                    .get("vpnconn_remote_netmask")
                )
                next_net = (
                    vms[i].params.object_params(vpns[i]).get("vpnconn_remote_net")
                )
                next_mask = (
                    vms[i].params.object_params(vpns[i]).get("vpnconn_remote_netmask")
                )
            else:
                prev_net = (
                    vms[i - 1]
                    .params.object_params(vpns[i - 1])
                    .get("vpnconn_remote_net")
                )
                prev_mask = (
                    vms[i - 1]
                    .params.object_params(vpns[i - 1])
                    .get("vpnconn_remote_netmask")
                )
                next_net = (
                    vms[i + 1]
                    .params.object_params(vpns[i + 1])
                    .get("vpnconn_remote_net")
                )
                next_mask = (
                    vms[i + 1]
                    .params.object_params(vpns[i + 1])
                    .get("vpnconn_remote_mask")
                )
            logging.debug(
                "Retrieved previous network %s/%s and next network %s/%s",
                prev_net,
                prev_mask,
                next_net,
                next_mask,
            )

            local1 = {
                "type": "custom",
                "lnet": prev_net,
                "lmask": prev_mask,
                "rnet": next_net,
                "rmask": next_mask,
            }

            vms[i].params["vpnconn_remote_net_%s" % fvpn] = next_net
            vms[i + 1].params["vpnconn_remote_net_%s" % fvpn] = prev_net

            self.configure_tunnel_between_vms(
                fvpn,
                vms[i],
                vms[i + 1],
                local1,
                remote1,
                peer1,
                auth,
                extra_apply_options,
            )

    """VM network test methods"""

    def get_tunnel_accessible_ip(
        self, src_vm: VM, dst_vm: VM, dst_nic: str = "lan_nic"
    ) -> str:
        """
        Get an accessible IP from a vm to a vm.

        Use heuristics about the tunnels and netconfigs of the entire vm network.

        :param src_vm: source vm whose IPs are starting points
        :param dst_vm: destination vm whose IPs are ending points
        :param dst_nic: network interface for the destination vm
        :returns: the IP with which the destination vm can be accessed from the source vm
        :raises: :py:class:`exceptions.TestError` if the destination server is not a server or
            the source or destination vms are not connected by a tunnel

        This ip can then be used for ping, tcp tests, etc.
        """
        dst_node = self.nodes[dst_vm.name]
        if dst_node.ephemeral:
            # ephemeral clients have only one interface
            dst_iface = dst_node.get_single_interface()
            server_node = dst_iface.netconfig.interfaces[
                dst_iface.netconfig.gateway
            ].node
        else:
            dst_iface = dst_node.interfaces[dst_node.params[dst_nic]]
            server_node = self.nodes[dst_vm.name]

        node1, node2 = self.nodes[src_vm.name], self.nodes[dst_vm.name]
        for id, tunnel in self.tunnels.items():
            if tunnel.connects_nodes(node1, node2):
                logging.debug(
                    "Found a tunnel with id %s between %s and %s",
                    id,
                    src_vm.name,
                    dst_vm.name,
                )
                break
        else:
            raise exceptions.TestError(
                "The source %s and destination %s are not connected by a tunnel"
                % (src_vm.name, dst_vm.name)
            )
        tunnel_params = (
            tunnel.left_params if server_node == tunnel.left else tunnel.right_params
        )

        # try to get translated ip (NAT) and if not get inner ip which is used
        # in the default tunnel configuration
        if self.nodes[dst_vm.name].ephemeral:
            nat_ip_server = tunnel_params.get("ip_nat")
            if nat_ip_server is not None:
                logging.debug(
                    "Obtaining translated IP address of an ephemeral client %s",
                    dst_vm.name,
                )
                nat_ip = dst_iface.netconfig.translate_address(
                    dst_iface.ip, nat_ip_server
                )
                logging.debug(
                    "Retrieved network translated ip %s for %s", nat_ip, dst_vm.name
                )
            else:
                nat_ip = dst_iface.ip
                logging.debug("Retrieved original ip %s for %s", nat_ip, dst_vm.name)
        else:
            nat_ip = tunnel_params.get("ip_nat", dst_iface.ip)
            logging.debug(
                "Retrieved network translated ip %s for %s", nat_ip, dst_vm.name
            )
        return nat_ip

    def get_accessible_ip(
        self, src_vm: VM, dst_vm: VM, dst_nic: str = "lan_nic"
    ) -> str:
        """
        Get an accessible IP from a vm to a vm.

        Use heuristics about the tunnels and netconfigs of the entire vm network.

        :param src_vm: source vm whose IPs are starting points
        :param dst_vm: destination vm whose IPs are ending points
        :param dst_nic: network interface role for the destination vm
        :returns: the IP with which the destination vm can be accessed from the source vm

        This ip can then be used for ping, tcp tests, etc.
        """
        logging.debug(
            "Searching for IP of %s that is accessible to %s", dst_vm.name, src_vm.name
        )
        dst_node = self.nodes[dst_vm.name]
        if dst_node.ephemeral:
            # ephemeral clients have only one interface
            dst_iface = dst_node.get_single_interface()
            dst_vm_server = dst_iface.netconfig.interfaces[
                dst_iface.netconfig.gateway
            ].node.platform
        else:
            dst_iface = self.interfaces[
                "%s.%s" % (dst_vm.name, dst_node.params[dst_nic])
            ]
            dst_vm_server = self.nodes[dst_vm.name].platform
        logging.debug("Detected destination server is %s", dst_vm_server.name)

        # check if the source vm shares a network with a fixed destination nic
        src_node = self.nodes[src_vm.name]
        for src_iface in src_node.interfaces.values():
            if src_iface.netconfig == dst_iface.netconfig:
                logging.debug(
                    "Internal IP %s of %s is accessible to %s",
                    dst_iface.ip,
                    dst_vm.name,
                    src_vm.name,
                )
                return str(dst_iface.ip)

        # TODO: we could also do some general routing and gateway search but this is
        # rather unnecessary with the current user requirements

        # do a tunnel search as the last resort (of what we have implemented so far)
        logging.debug(
            "No accessible IP found in local networks, falling back to tunnel search"
        )
        return self.get_tunnel_accessible_ip(src_vm, dst_vm, dst_nic=dst_nic)

    def verify_vpn_in_log(
        self, src_vm: VM, dst_vm: VM, log_vm: VM = None, require_blocked: bool = False
    ) -> None:
        """
        Search for the appropriate message in the vpn log file.

        :param src_vm: source vm whose packets will be logged
        :param dst_vm: destination vm whose packets will be logged
        :param log_vm: vm where all packets are logged
        :param require_blocked: whether to expect access message or deny message
        :raises: :py:class:`exceptions.TestError` if the source or destination vms are not on the network
        :raises: :py:class:`exceptions.TestFail` if the VPN packets were not logged properly

        This function requires modified firewall ruleset for the vpn connection.
        """
        if log_vm is None:
            log_vm = dst_vm

        node1, node2 = self.nodes[src_vm.name], self.nodes[dst_vm.name]
        for id, tunnel in self.tunnels.items():
            if tunnel.connects_nodes(node1, node2):
                logging.debug(
                    "Found a vpn connection with id %s between %s and %s",
                    id,
                    src_vm.name,
                    dst_vm.name,
                )
                vpn = tunnel
                left_index, right_index = re.match(r"^vpn(\d+)\.(\d+)\w*", id).group(
                    1, 2
                )
                break
        else:
            raise exceptions.TestError(
                "The source %s and destination %s are not connected by a tunnel"
                % (src_vm.name, dst_vm.name)
            )

        if log_vm == vpn.left.platform:
            log_index = int(left_index)
            remote_index = int(right_index)
        elif log_vm == vpn.right.platform:
            log_index = int(right_index)
            remote_index = int(left_index)
        else:
            raise exceptions.TestError(
                "The logging vm %s must be one of the VPN endpoints %s or %s"
                % (log_vm.name, src_vm.name, dst_vm.name)
            )
        log_message = (
            "VPN%i.%i" % (log_index, remote_index)
            if log_vm == vpn.left.platform
            else "VPN%i.%i" % (remote_index, log_index)
        )
        deny_message = "%s_DENY" % log_message

        logging.info(
            "Checking log of %s for the firewall rule tag %s ", log_vm.name, log_message
        )
        log = log_vm.session.cmd("cat /var/log/messages")
        if require_blocked:
            if re.match(log_message + r"\s", log) is not None:
                raise exceptions.TestFail(
                    "The access message %s was found in log" % log_message
                )
            if deny_message not in log:
                raise exceptions.TestFail(
                    "The deny message %s was not found in log" % deny_message
                )
        else:
            if log_message not in log:
                raise exceptions.TestFail(
                    "The access message %s was not found in log" % log_message
                )
            if deny_message in log:
                raise exceptions.TestFail(
                    "The deny message %s was found in log" % deny_message
                )
        for message in re.findall(r"VPN_%i\.\d+" % log_index, log):
            if message != log_message:
                raise exceptions.TestFail(
                    "Wrong message %s in addition to %s was found in log"
                    % (message, log_message)
                )
        logging.info("Ok, resetting the messages log at %s", log_vm.name)
        log_vm.session.cmd("rm -f /var/log/messages")
        log_vm.session.cmd("/etc/init.d/rsyslog restart")

    def ping(
        self, src_vm: VM, dst_vm: VM, dst_nic: str = "lan_nic", address: str = None
    ) -> tuple[int, str]:
        """
        Pings a vm from another vm to test basic ICMP connectivity.

        :param src_vm: source vm which will ping
        :param dst_vm: destination vm which will be pinged
        :param dst_nic: nic of the destination vm used if necessary to obtain accessible IP
        :param address: explicit IP or domain to use for pinging
        :returns: the status and output of the performed ping

        If no `address` is provided, the IP is obtained by analyzing the network topology
        from `src_vm` to `dst_vm`.

        If no `dst_vm` is provided, the ping happens directly to `address`.
        """
        if address is None:
            address = self.get_accessible_ip(src_vm, dst_vm, dst_nic=dst_nic)

        logging.info("Pinging %s (%s) from %s", dst_vm.name, address, src_vm.name)
        count_limit = (
            "" if src_vm.params.get("os_type", "linux") == "windows" else "-c 3"
        )
        return src_vm.session.cmd_status_output("ping %s %s" % (address, count_limit))

    def ping_validate(
        self,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        timeout: int = 30,
    ) -> None:
        """
        Pings a vm from another vm to test basic ICMP connectivity and bails on nonzero status.

        Arguments are similar to the ones from :py:meth:`ping` with the exception of:

        :param timeout: number of seconds to retry the ping for as networking
                            might not be immediately available
        :raises: :py:class:`exceptions.TestError` if the performed ping failed

        This method does not perform a refined exit status check, you can use the non-validated
        version and perform your own customization if you wish.
        """
        for _ in range(timeout):
            status, output = self.ping(src_vm, dst_vm, dst_nic=dst_nic, address=address)
            if status == 0:
                break
            time.sleep(1)

        if status != 0:
            raise exceptions.TestError(
                "Ping of %s from %s unsuccessful" % (dst_vm.name, src_vm.name)
            )
        else:
            logging.debug(output.split("\n")[-3])

    def ping_all(self, timeout: int = 30) -> None:
        """
        Pings all nodes from each other in order to test complete basic ICMP connectivity.

        :param timeout: number of seconds to retry the ping for as networking
                            might not be immediately available
        :raises: :py:class:`exceptions.TestError` if a network mutual ping failed

        The ping happens among all LAN members, throwing an exception if one of the pings fails.
        """
        logging.info(
            "Commencing mutual ping of %d vms (including self ping).", len(self.nodes)
        )
        failed = False

        for node1 in self.nodes.values():
            for interface1 in node1.interfaces.values():
                for node2 in self.nodes.values():
                    for interface2 in node2.interfaces.values():
                        for netconfig in self.netconfigs.values():
                            if (
                                interface1.ip in netconfig.interfaces
                                and interface2.ip in netconfig.interfaces
                            ):
                                direction_str = "%s (%s) from %s (%s)" % (
                                    node2.name,
                                    interface2.ip,
                                    node1.name,
                                    interface1.ip,
                                )
                                logging.debug("Pinging %s", direction_str)
                                for _ in range(timeout):
                                    status, output = self.ping(
                                        node1.platform,
                                        node2.platform,
                                        address=interface2.ip,
                                    )
                                    if status == 0:
                                        break
                                    time.sleep(1)
                                logging.debug(
                                    "Pinging returned status %s and output:\n%s",
                                    status,
                                    output,
                                )
                                failed = failed or status != 0

        if failed:
            raise exceptions.TestError("Mutual ping of all LAN members unsuccessful")
        logging.info("Mutual ping of all LAN members successful")

    def port_connectivity(
        self,
        msg: str,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 80,
        protocol: str = "TCP",
    ) -> tuple[int, str]:
        """
        Test connectivity using a predefined port (usually in addition to pinging).

        Arguments are similar to the :py:meth:`ping` method with the exception of:

        :param msg: probing data to be sent to the port
        :param port: forwarding port to send the message to
        :param protocol: protocol type (TCP, UDP or something over them)
        :returns: the result of the performed port connection attempt
        """
        if address is None:
            address = self.get_accessible_ip(src_vm, dst_vm, dst_nic=dst_nic)

        logging.info(
            "Connecting from %s to %s (%s) at %s port %s",
            src_vm.name,
            dst_vm.name,
            address,
            protocol,
            port,
        )
        src_vm.session.sendline(
            "cat <<EOF | socat - %s:%s:%s,connect-timeout=3" % (protocol, address, port)
        )
        src_vm.session.sendline(msg)

        status, output = src_vm.session.cmd_status_output("EOF", safe=True)
        logging.debug(
            "Status %s and output from the connection attempt:\n%s", status, output
        )
        return status, output

    def port_connectivity_validate(
        self,
        msg: str,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 80,
        protocol: str = "TCP",
        validate_output: str = "",
        require_blocked: bool = False,
    ) -> None:
        """
        Test connectivity using a predefined port (usually in addition to pinging).

        Arguments are similar to the :py:meth:`port_connectivity` method with the exception of:

        :param validate_output: string to find in the command output and validate against
        :param require_blocked: whether to expect nonzero status from the connection attempt
        :raises: :py:class:`exceptions.TestError` if the performed port connection attempt failed

        This method does not perform a refined exit status check, you can use the non-validated
        version and perform your own customization if you wish.
        """
        status, output = self.port_connectivity(
            msg,
            src_vm,
            dst_vm,
            dst_nic=dst_nic,
            address=address,
            port=port,
            protocol=protocol,
        )

        status_condition = status != 0 if require_blocked else status == 0
        if status_condition:
            logging.info("Port %s connection status matched", port)
        else:
            state = "reachable" if require_blocked else "unreachable"
            raise exceptions.TestError(
                "Port of %s (%s:%s) is %s from %s"
                % (dst_vm.name, address, port, state, src_vm.name)
            )

        output_condition = (
            validate_output not in output
            if require_blocked
            else validate_output in output
        )
        if output_condition:
            state = "blocked" if require_blocked else "succeeded"
            logging.info("Connection %s as expected", state)
        else:
            state = "not blocked" if require_blocked else "failed"
            raise exceptions.TestFail(
                "Connecting the port %s %s with the following outputs:\n%s"
                % (port, state, output)
            )

    def http_connectivity(
        self,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 80,
        protocol: str = "HTTP",
    ) -> tuple[int, str]:
        """
        Test connectivity using an HTTP port and protocol.

        Arguments are similar to the :py:meth:`port_connectivity` method.

        :raises: :py:class:`exceptions.TestError` if inappropriate protocol was given
        """
        logging.debug("Sending probing data for the HTTP protocol")
        if protocol != "HTTP":
            raise exceptions.TestError(
                "Invalid protocol for HTTP port connectivity: %s" % protocol
            )
        return self.port_connectivity(
            "GET / HTTP/1.0", src_vm, dst_vm, dst_nic, address, port, "TCP"
        )

    def http_connectivity_validate(
        self,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 80,
        protocol: str = "HTTP",
        require_blocked: bool = False,
    ) -> None:
        """
        Test connectivity using an HTTP port and protocol.

        Arguments are similar to the :py:meth:`port_connectivity` method.

        :raises: :py:class:`exceptions.TestError` if inappropriate protocol was given
        """
        logging.debug("Sending probing data for the HTTP protocol")
        if protocol != "HTTP":
            raise exceptions.TestError(
                "Invalid protocol for HTTP port connectivity: %s" % protocol
            )
        return self.port_connectivity_validate(
            "GET / HTTP/1.0",
            src_vm,
            dst_vm,
            dst_nic,
            address,
            port,
            "TCP",
            validate_output="HTML",
            require_blocked=require_blocked,
        )

    def https_connectivity(
        self,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 443,
        protocol: str = "HTTPS",
    ) -> tuple[int, str]:
        """
        Test connectivity using an HTTPS port and protocol.

        Arguments are similar to the :py:meth:`port_connectivity` method.

        :raises: :py:class:`exceptions.TestError` if inappropriate protocol was given
        """
        logging.debug("Sending probing data for the HTTPS protocol")
        if address is None:
            address = self.get_accessible_ip(src_vm, dst_vm, dst_nic=dst_nic)
        if protocol != "HTTPS":
            raise exceptions.TestError(
                "Invalid protocol for HTTPS port connectivity: %s" % protocol
            )
        address = "%s://%s:%s" % (protocol.lower(), address, port)
        # make self-signed certificates nonfatal for the HTTPS probing
        cmd = "curl -k " + address
        status, output = src_vm.session.cmd_status_output(cmd)
        logging.debug("Got status %s and page content:\n%s", status, output)
        return status, output

    def https_connectivity_validate(
        self,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 443,
        protocol: str = "HTTPS",
        require_blocked: bool = False,
    ) -> None:
        """
        Test connectivity using an HTTPS port and protocol.

        Arguments are similar to the :py:meth:`port_connectivity` method.

        :raises: :py:class:`exceptions.TestError` if inappropriate protocol was given
        """
        status, output = self.https_connectivity(
            src_vm,
            dst_vm,
            dst_nic=dst_nic,
            address=address,
            port=port,
            protocol=protocol,
        )
        if require_blocked:
            if status == 0 and "HTML" in output:
                raise exceptions.TestFail(
                    "HTTPS connection to %s succeeded with the following outputs:\n%s"
                    % (port, output)
                )
        else:
            if status != 0 and "HTML" not in output:
                raise exceptions.TestFail(
                    "HTTPS connection to %s failed with the following outputs:\n%s"
                    % (port, output)
                )

    def ssh_connectivity(
        self,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 22,
        protocol: str = "SSH",
    ) -> tuple[int, str]:
        """
        Test connectivity using an SSH port and protocol.

        Arguments are similar to the :py:meth:`port_connectivity` method.

        :raises: :py:class:`exceptions.TestError` if inappropriate protocol was given
        """
        logging.debug("Sending probing data for the SSH protocol")
        if protocol != "SSH":
            raise exceptions.TestError(
                "Invalid protocol for SSH port connectivity: %s" % protocol
            )
        return self.port_connectivity(
            "test", src_vm, dst_vm, dst_nic, address, port, "TCP"
        )

    def ssh_connectivity_validate(
        self,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 22,
        protocol: str = "SSH",
        require_blocked: bool = False,
    ) -> None:
        """
        Test connectivity using an SSH port and protocol.

        Arguments are similar to the :py:meth:`port_connectivity` method.

        :raises: :py:class:`exceptions.TestError` if inappropriate protocol was given
        """
        logging.debug("Sending probing data for the SSH protocol")
        if protocol != "SSH":
            raise exceptions.TestError(
                "Invalid protocol for SSH port connectivity: %s" % protocol
            )
        return self.port_connectivity_validate(
            "test",
            src_vm,
            dst_vm,
            dst_nic,
            address,
            port,
            "TCP",
            validate_output="OpenSSH",
            require_blocked=require_blocked,
        )

    def _ssh_client_hostname(
        self, src_vm: VM, dst_vm: VM, ssh_ip: str, timeout: int = 10
    ) -> str:
        logging.info(
            "Retrieving host name of client %s from %s through ip %s",
            dst_vm.name,
            src_vm.name,
            ssh_ip,
        )
        dump = src_vm.session.cmd(
            'echo "" | '
            "ssh -o StrictHostKeyChecking=no "
            "-o UserKnownHostsFile=/dev/null "
            "root@%s dhcpcd --dumplease eth0 | grep host_name" % ssh_ip
        )
        logging.debug(dump)
        dst_hostname_match = re.search(r"host_name=(\w+)", dump)
        if dst_hostname_match:
            dst_hostname = dst_hostname_match.group(1)
            logging.info("Reported host name is %s", dst_hostname)
            return dst_hostname
        raise exceptions.TestFail("No client host name found")

    def _ssh_server_hostname(
        self, src_vm: VM, dst_vm: VM, ssh_ip: str, timeout: int = 10
    ) -> str:
        logging.info(
            "Retrieving host name of server %s from %s through ip %s",
            dst_vm.name,
            src_vm.name,
            ssh_ip,
        )
        src_vm.session.sendline(
            "ssh -o StrictHostKeyChecking=no "
            "-o UserKnownHostsFile=/dev/null "
            "root@%s hostname" % ssh_ip
        )
        expected_lines = [r"[Pp]assword:\s*$", r".*"]
        for _ in range(timeout):
            time.sleep(1)
            match, text = src_vm.session.read_until_last_line_matches(
                expected_lines, timeout=timeout, internal_timeout=0.5
            )
            logging.debug("Got answer:\n%s", text)
            if match == 0:
                logging.debug("Got password prompt, sending password")
                src_vm.session.sendline(dst_vm.params.get("password"))
            elif match == 1:
                # the extra search is due to the inability of the builtin command to match the host
                # therefore internally match all and perform the actual matching here
                dst_hostname_match = re.search(r"(\w+)\.[a-zA-Z]+", text)
                if dst_hostname_match:
                    dst_hostname = dst_hostname_match.group(1)
                    logging.info("Reported host name is %s", dst_hostname)
                    return dst_hostname
        raise exceptions.TestFail("No server host name found")

    def ssh_hostname(
        self, src_vm: VM, dst_vm: VM, dst_nic: str = "lan_nic", timeout: int = 10
    ) -> str:
        """
        Get the host name of a vm from any other vm in the vm net using the SSH protocol.

        :param src_vm: source vm with the SSH client
        :param dst_vm: destination vm with the SSH server
        :param dst_nic: nic of the destination vm used if necessary to obtain accessible IP
        :param timeout: timeout for the SSH connection
        :returns: the hostname of the SSH server

        This tests the TCP connectivity and verifies it leads to the
        correct machine.
        """
        ssh_ip = self.get_accessible_ip(src_vm, dst_vm, dst_nic=dst_nic)
        if self.nodes[dst_vm.name].ephemeral:
            return self._ssh_client_hostname(src_vm, dst_vm, ssh_ip, timeout)
        else:
            return self._ssh_server_hostname(src_vm, dst_vm, ssh_ip, timeout)

    def scp_files(
        self,
        src_path: str,
        dst_path: str,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        timeout: int = 10,
    ) -> None:
        """
        Copy files securely where built-in methods like :py:func:`vm.copy_files_to` fail.

        :param src_path: source path for the securely copied files
        :param dst_path: destination path for the securely copied files
        :param src_vm: source vm with the ssh client
        :param dst_vm: destination vm with the ssh server
        :param dst_nic: nic of the destination vm used if necessary to obtain accessible IP
        :param timeout: timeout for the SSH connection
        :raises: :py:class:`exceptions.TestFail` if the files couldn't be copied

        The paths `src_path` and `dst_path` must be strings, possibly with a wildcard.
        """
        ssh_ip = self.get_accessible_ip(src_vm, dst_vm, dst_nic=dst_nic)
        logging.info(
            "Copying files %s from %s to %s", src_path, src_vm.name, dst_vm.name
        )
        src_vm.session.sendline(
            "scp -O "
            "-o StrictHostKeyChecking=no "
            "-o UserKnownHostsFile=/dev/null "
            "-P %s %s root@%s:%s"
            % (dst_vm.params.get("file_transfer_port", 22), src_path, ssh_ip, dst_path)
        )
        expected_lines = [r"[Pp]assword:\s*$", r".*"]
        for _ in range(timeout):
            time.sleep(1)
            match, text = src_vm.session.read_until_last_line_matches(
                expected_lines, timeout=timeout, internal_timeout=0.5
            )
            logging.debug("Got answer:\n%s", text)
            if match == 0:
                logging.debug("Got password prompt, sending password")
                src_vm.session.sendline(dst_vm.params.get("password"))
            elif match == 1:
                # the extra search is due to the inability of the builtin command to match the host
                # therefore internally match all and perform the actual matching here
                file_transfer = re.search(r"ETA(.+\s+100%.+)", text)
                if file_transfer:
                    logging.info(file_transfer.group(1))
                    return
        raise exceptions.TestFail(
            "No file progress bars were found - couldn't copy %s" % src_path
        )

    def ftp_connectivity(
        self,
        msg: str,
        file: str | None,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 21,
    ) -> tuple[int, str]:
        """
        Send file request to an FTP destination port and address and verify it was received.

        Arguments are similar to the :py:meth:`port_connectivity` method with the exception of:

        :param file: file to retrieve containing the test data or none if sent directly
        :raises: :py:class:`exceptions.TestError` if inappropriate protocol was given
        """
        logging.debug("Sending the data '%s' in a file %s", msg, file)
        if address is None:
            address = self.get_accessible_ip(src_vm, dst_vm, dst_nic=dst_nic)
        protocol = "FTP"

        address = "%s://%s:%s/%s" % (protocol.lower(), address, port, file)
        credentials = "%s:%s" % (
            src_vm.params["ftp_username"],
            src_vm.params["ftp_password"],
        )
        cmd = "curl -u %s --disable-epsv %s" % (credentials, address)
        status, output = src_vm.session.cmd_status_output(cmd)
        logging.debug("Got status %s and file content:\n%s", status, output)
        return status, output

    def ftp_connectivity_validate(
        self,
        msg: str,
        file: str | None,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 21,
        require_blocked: bool = False,
    ) -> None:
        """
        Send file request to an FTP destination port and address and verify it was received.

        Arguments are similar to the :py:meth:`port_connectivity` method with the exception of:

        :param file: file to retrieve containing the test data or none if sent directly
        :raises: :py:class:`exceptions.TestError` if inappropriate protocol was given
        """
        status, output = self.ftp_connectivity(
            msg, file, src_vm, dst_vm, dst_nic=dst_nic, address=address, port=port
        )
        if require_blocked:
            if status == 0 and msg in output:
                raise exceptions.TestFail(
                    "FTP connection to %s failed with the following outputs:\n%s"
                    % (port, output)
                )
        else:
            if status != 0 and msg not in output:
                raise exceptions.TestFail(
                    "FTP connection to %s succeeded with the following outputs:\n%s"
                    % (port, output)
                )

    def tftp_connectivity(
        self,
        msg: str,
        file: str | None,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 69,
    ) -> tuple[int, str]:
        """
        Send file request to an TFTP destination port and address and verify it was received.

        Arguments are similar to the :py:meth:`port_connectivity` method with the exception of:

        :param file: file to retrieve containing the test data or none if sent directly
        :raises: :py:class:`exceptions.TestError` if inappropriate protocol was given
        """
        logging.debug("Sending the data '%s' in a file %s", msg, file)
        if address is None:
            address = self.get_accessible_ip(src_vm, dst_vm, dst_nic=dst_nic)
        protocol = "TFTP"

        address = "%s://%s:%s/%s" % (protocol.lower(), address, port, file)
        cmd = "curl " + address
        status, output = src_vm.session.cmd_status_output(cmd)
        logging.debug("Got status %s and file content:\n%s", status, output)
        return status, output

    def tftp_connectivity_validate(
        self,
        msg: str,
        file: str | None,
        src_vm: VM,
        dst_vm: VM,
        dst_nic: str = "lan_nic",
        address: str = None,
        port: int = 69,
        require_blocked: bool = False,
    ) -> None:
        """
        Send file request to an TFTP destination port and address and verify it was received.

        Arguments are similar to the :py:meth:`port_connectivity` method with the exception of:

        :param file: file to retrieve containing the test data or none if sent directly
        :raises: :py:class:`exceptions.TestError` if inappropriate protocol was given
        """
        status, output = self.tftp_connectivity(
            msg, file, src_vm, dst_vm, dst_nic=dst_nic, address=address, port=port
        )
        if require_blocked:
            if status == 0 and msg in output:
                raise exceptions.TestFail(
                    "TFTP connection to %s failed with the following outputs:\n%s"
                    % (port, output)
                )
        else:
            if status != 0 and msg not in output:
                raise exceptions.TestFail(
                    "TFTP connection to %s succeeded with the following outputs:\n%s"
                    % (port, output)
                )
