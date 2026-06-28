#!/usr/bin/env python

import unittest
import unittest.mock as mock
import shutil
import re

from avocado import Test
from avocado.core import exceptions
from virttest import utils_params

import unittest_importer
from avocado_i2n import vmnet
from avocado_i2n.vmnet import VMNetwork


class VMNetworkTest(Test):

    def setUp(self):
        self.vmnet = mock.MagicMock()
        self.run_params = utils_params.Params()
        self.run_params["vms"] = "vm1 vm2"
        self.run_params["roles"] = "node1 node2"
        self.run_params["node1"] = "vm1"
        self.run_params["node2"] = "vm2"
        self.run_params["nics"] = "b1 b2"
        self.run_params["nic_roles"] = "internet_nic lan_nic"
        self.run_params["internet_nic"] = "b1"
        self.run_params["lan_nic"] = "b2"
        self.run_params["mac"] = "00:00:00:00:00:00"
        self.run_params["netmask_b1"] = "255.255.0.0"
        self.run_params["netmask_b2"] = "255.255.0.0"
        self.run_params["ip_b1_vm1"] = "10.1.0.1"
        self.run_params["ip_b2_vm1"] = "172.17.0.1"
        self.run_params["ip_b1_vm2"] = "10.2.0.1"
        self.run_params["ip_b2_vm2"] = "172.18.0.1"
        self.run_params["netdst_b1_vm1"] = "virbr0"
        self.run_params["netdst_b2_vm1"] = "virbr1"
        self.run_params["netdst_b1_vm2"] = "virbr2"
        self.run_params["netdst_b2_vm2"] = "virbr3"

        self.env = mock.MagicMock(name='env')
        self.env.get_vm = mock.MagicMock(side_effect=self._get_mock_vm)
        self.env.create_vm = mock.MagicMock(side_effect=self._create_mock_vm)

        self.mock_vms = {}

    def _get_mock_vm(self, vm_name):
        return None if vm_name not in self.mock_vms else self.mock_vms[vm_name]

    def _create_mock_vm(self, vm_type, target, vm_name, vm_params, bindir):
        self.mock_vms[vm_name] = mock.MagicMock(name=vm_name)
        self.mock_vms[vm_name].name = vm_name
        self.mock_vms[vm_name].params = vm_params
        return self.mock_vms[vm_name]

    def _create_mock_vms(self):
        for vm_name in self.run_params.objects("vms"):
            self._create_mock_vm("qemu", None, vm_name,
                                 self.run_params.object_params(vm_name), "")

    def test_representation(self):
        """Test for correct vm network and component representations."""
        self.vmnet = VMNetwork(self.run_params, self.env)
        repr = str(self.vmnet)
        self.assertIn("[vmnet]", repr)
        self.assertIn("[node]", repr)
        self.assertIn("[iface]", repr)
        self.assertIn("[net]", repr)

    def test_get_vms(self):
        """Test all vm retrieval methods."""
        self.run_params["vms"] = "vm1"
        self.vmnet = VMNetwork(self.run_params, self.env)
        vm = self.vmnet.get_single_vm()
        self.assertEqual(vm.name, "vm1")
        vm, session = self.vmnet.get_single_vm_with_session()
        self.assertEqual(vm.name, "vm1")
        self.assertEqual(vm.session, session)
        self.vmnet.nodes["vm1"].last_session = None
        vm, session, params = self.vmnet.get_single_vm_with_session_and_params()
        self.assertEqual(vm.name, "vm1")
        self.assertEqual(vm.session, session)
        self.assertEqual(vm.params, params)

        self.run_params["vms"] = "vm1 vm2"
        self.vmnet = VMNetwork(self.run_params, self.env)
        with self.assertRaises(exceptions.TestError):
            self.vmnet.get_single_vm()
        vm1, vm2 = self.vmnet.get_ordered_vms()
        self.assertEqual(vm1.name, "vm1")
        self.assertEqual(vm2.name, "vm2")
        vm1, vm2 = self.vmnet.get_ordered_vms(2)
        self.assertEqual(vm1.name, "vm1")
        self.assertEqual(vm2.name, "vm2")
        with self.assertRaises(exceptions.TestError):
            vm1 = self.vmnet.get_ordered_vms(1)
        vms = self.vmnet.get_vms()
        vm1, vm2 = vms.node1, vms.node2
        self.assertEqual(vm1.name, "vm1")
        self.assertEqual(vm2.name, "vm2")
        self.vmnet.params["roles"] = "node1 node2 node3"
        self.vmnet.params["node2"] = None
        with self.assertRaises(exceptions.TestError):
            self.vmnet.get_vms()

    def test_integrate_node(self):
        """Test correct vm node integration and network generation."""
        # repeated vm node in the net
        self.vmnet = VMNetwork(self.run_params, self.env)
        node1 = self.vmnet.nodes["vm1"]
        with self.assertRaises(AssertionError):
            self.vmnet.integrate_node(node1)

        # already initialized interfaces
        self.run_params["vms"] = "vm2"
        self.vmnet = VMNetwork(self.run_params, self.env)
        with self.assertRaises(AssertionError):
            self.vmnet.integrate_node(node1)

        # correct case (ininitialized vm node interfaces)
        node1.interfaces.clear()
        self.vmnet.integrate_node(node1)

        # repeated address in the netconfig
        self.run_params["ip_b1_vm2"] = "10.1.0.1"
        self.vmnet = VMNetwork(self.run_params, self.env)
        node1.interfaces.clear()
        # BUG: this test succeeds in full module run locally but not in the CI
        #with self.assertRaises(IndexError):
        #    self.vmnet.integrate_node(node1)

    def test_reattach_interface(self):
        """Test vm node reattachment to another vm node's interface."""
        self._create_mock_vms()
        self.vmnet = VMNetwork(self.run_params, self.env)
        client, server = self.vmnet.get_vms()
        self.vmnet.reattach_interface(client, server)
        self.vmnet.reattach_interface(client, server, proxy_nic="b1")

    @mock.patch('avocado_i2n.vmnet.network.os.rename', mock.Mock(return_value=0))
    @mock.patch('avocado_i2n.vmnet.network.process', mock.Mock())
    @mock.patch('avocado_i2n.vmnet.network.utils_net')
    def test_host_networking(self, utils_net):
        """Test host networking services like DHCP, DNS, firewall, and bridges."""
        self.run_params["ip_provider_b1_vm1"] = "10.1.0.254"
        self.run_params["host_b1_vm1"] = "10.1.0.254"
        self.run_params["host_set_bridge_b1_vm1"] = "yes"
        self.run_params["permanent_netdst_b1_vm1"] = "no"
        self.run_params["host_services_b1_vm1"] = "yes"
        self.run_params["ip_provider_b1_vm2"] = "10.2.0.1"
        self.run_params["host_b1_vm2"] = ""
        self._create_mock_vms()

        # nonauthoritative service setup
        self.vmnet = VMNetwork(self.run_params, self.env)
        vmnet.network.DNSMASQ_CONFIG = "avocado.conf"
        vmnet.network.DNSMASQ_HOSTS = "avocado-hosts.conf"
        self.vmnet.setup_host_services()

        # authoritative service setup
        vmnet.network.BIND_DHCP_CONFIG = "dhcpd.conf"
        vmnet.network.BIND_DNS_CONFIG = "named.conf"
        vmnet.network.BIND_DECLARATIONS = "."
        self.run_params["host_dhcp_authoritative"] = "yes"
        self.run_params["host_dns_authoritative"] = "yes"
        self.run_params["default_dns_forwarder"] = "8.8.8.8"
        self.run_params["domain_provider"] = "lan.net"
        self.vmnet = VMNetwork(self.run_params, self.env)
        self.vmnet.setup_host_services()

        # additional ports could be added
        self.run_params["host_additional_ports"] = "22"
        self.vmnet = VMNetwork(self.run_params, self.env)
        self.vmnet.setup_host_services()
        # blacklisted devices cannot be managed
        self.vmnet.params["host_dhcp_blacklist"] = "virbr0 virbr1"
        with self.assertRaises(exceptions.TestError):
            self.vmnet.setup_host_services()
        self.vmnet.params["host_dhcp_blacklist"] = "virbr1"
        self.vmnet.setup_host_services()
        self.run_params["host_dns_blacklist"] = "virbr0 virbr1"
        with self.assertRaises(exceptions.TestError):
            self.vmnet.setup_host_services()

        self.vmnet = VMNetwork(self.run_params, self.env)
        utils_net.find_bridge_manager.get_structure.return_value = ["virbr0", "virbr2"]
        self.vmnet.setup_host_bridges()
        utils_net.find_bridge_manager.return_value = None
        self.vmnet.setup_host_bridges()

    def test_spawn_clients(self):
        """Test ephemeral client spawninig."""
        self._create_mock_vms()
        self.vmnet = VMNetwork(self.run_params, self.env)

        # TODO: this method still lacks complete noncustom (available) implementation
        with self.assertRaises(NotImplementedError):
            self.vmnet.spawn_clients("vm1", 1)

        self.vmnet._register_client_at_server = mock.MagicMock()
        self.vmnet.spawn_clients("vm1", 1)

    def test_change_network_address(self):
        """Test network address changing."""
        self.run_params["os_type"] = "windows"
        self.vmnet = VMNetwork(self.run_params, self.env)
        netconfig = self.vmnet.netconfigs["10.1.0.0"]
        self.vmnet.change_network_address(netconfig, "10.3.0.1")
        netconfig = self.vmnet.netconfigs["10.2.0.0"]
        self.vmnet.change_network_address(netconfig, "10.2.0.1", "255.255.0.0")

    def test_set_static_address(self):
        """Test static network address setting."""
        self.run_params["os_type"] = "windows"
        self.vmnet = VMNetwork(self.run_params, self.env)
        client, server = self.vmnet.get_vms()
        self.vmnet.set_static_address(client, server)

        # test nonexisting (unsupported) guest os variants
        self._create_mock_vms()
        self.run_params["os_type"] = "imaginary"
        self.run_params["os_variant"] = "i2"
        self.vmnet = VMNetwork(self.run_params, self.env)
        client, server = self.vmnet.get_vms()
        with self.assertRaises(NotImplementedError):
            self.vmnet.set_static_address(client, server)

    def test_configure_tunnel_between_vms_basic(self):
        """Test a site-to-site tunnel setup and end-configuration between vms."""
        self._create_mock_vms()
        self.vmnet = VMNetwork(self.run_params, self.env)
        self.vmnet.configure_tunnel_between_vms("vpn1", self.mock_vms["vm1"], self.mock_vms["vm2"],
                                                local1={"type": "nic", "nic": "lan_nic"},
                                                remote1={"type": "custom", "nic": "lan_nic"},
                                                peer1={"type": "ip", "nic": "internet_nic"},
                                                auth=None)
        tunnel = self.vmnet.tunnels["vpn1"]

        # tunnel types
        self.assertEqual(tunnel.left_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.right_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.left_params['vpnconn_lan_type'], 'NIC')
        self.assertEqual(tunnel.right_params['vpnconn_lan_type'], 'NIC')
        self.assertEqual(tunnel.left_params['vpnconn_remote_type'], 'CUSTOM')
        self.assertEqual(tunnel.right_params['vpnconn_remote_type'], 'CUSTOM')
        self.assertEqual(tunnel.left_params['vpnconn_peer_type'], 'IP')
        self.assertEqual(tunnel.right_params['vpnconn_peer_type'], 'IP')

        # tunnel end points/sites
        self.assertEqual(tunnel.left_params['vpnconn_remote_net'], '172.18.0.0')
        self.assertEqual(tunnel.right_params['vpnconn_remote_net'], '172.17.0.0')
        self.assertEqual(tunnel.left_params['vpnconn_remote_netmask'], '255.255.0.0')
        self.assertEqual(tunnel.right_params['vpnconn_remote_netmask'], '255.255.0.0')
        self.assertEqual(tunnel.left_params['vpnconn_peer_ip'], '10.2.0.1')
        self.assertEqual(tunnel.right_params['vpnconn_peer_ip'], '10.1.0.1')
        self.assertEqual(tunnel.left_params['vpnconn_activation'], 'ALWAYS')
        self.assertEqual(tunnel.right_params['vpnconn_activation'], 'ALWAYS')

        # authentication
        self.assertEqual(tunnel.left_params['vpnconn_key_type'], 'NONE')
        self.assertEqual(tunnel.right_params['vpnconn_key_type'], 'NONE')

        # other
        self.assertTrue(tunnel.connects_nodes(tunnel.left, tunnel.right))
        self.assertIn("[tunnel]", str(tunnel))

    @mock.patch.object(vmnet.VMTunnel, 'configure_on_endpoint', mock.MagicMock())
    def test_configure_tunnel_between_vms_internetip(self):
        """Test a point-to-site tunnel setup and end-configuration between vms."""
        self._create_mock_vms()
        self.vmnet = VMNetwork(self.run_params, self.env)
        self.vmnet.configure_tunnel_between_vms("vpn1", self.mock_vms["vm1"], self.mock_vms["vm2"],
                                                local1={"type": "internetip"},
                                                remote1={"type": "custom", "nic": "lan_nic"},
                                                peer1={"type": "ip", "nic": "internet_nic"},
                                                auth=None)
        tunnel = self.vmnet.tunnels["vpn1"]

        self.assertEqual(tunnel.left_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.right_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.left_params['vpnconn_lan_type'], 'INTERNETIP')
        self.assertEqual(tunnel.right_params['vpnconn_lan_type'], 'NIC')
        self.assertEqual(tunnel.left_params['vpnconn_remote_type'], 'CUSTOM')
        self.assertEqual(tunnel.right_params['vpnconn_remote_type'], 'EXTERNALIP')
        self.assertEqual(tunnel.left_params['vpnconn_peer_type'], 'IP')
        self.assertEqual(tunnel.right_params['vpnconn_peer_type'], 'IP')

    @mock.patch.object(vmnet.VMTunnel, 'configure_on_endpoint', mock.MagicMock())
    def test_configure_tunnel_between_vms_externalip(self):
        """Test a site-to-point tunnel setup and end-configuration between vms."""
        self._create_mock_vms()
        self.vmnet = VMNetwork(self.run_params, self.env)
        self.vmnet.configure_tunnel_between_vms("vpn1", self.mock_vms["vm1"], self.mock_vms["vm2"],
                                                local1={"type": "nic", "nic": "lan_nic"},
                                                remote1={"type": "externalip"},
                                                peer1={"type": "ip", "nic": "internet_nic"},
                                                auth=None)
        tunnel = self.vmnet.tunnels["vpn1"]

        self.assertEqual(tunnel.left_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.right_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.left_params['vpnconn_lan_type'], 'NIC')
        self.assertEqual(tunnel.right_params['vpnconn_lan_type'], 'INTERNETIP')
        self.assertEqual(tunnel.left_params['vpnconn_remote_type'], 'EXTERNALIP')
        self.assertEqual(tunnel.right_params['vpnconn_remote_type'], 'CUSTOM')
        self.assertEqual(tunnel.left_params['vpnconn_peer_type'], 'IP')
        self.assertEqual(tunnel.right_params['vpnconn_peer_type'], 'IP')

    @mock.patch.object(vmnet.VMTunnel, 'configure_on_endpoint', mock.MagicMock())
    def test_configure_tunnel_between_vms_dynip(self):
        """Test a roadwarrior tunnel setup and end-configuration between vms."""
        self._create_mock_vms()
        self.vmnet = VMNetwork(self.run_params, self.env)
        self.vmnet.configure_tunnel_between_vms("vpn1", self.mock_vms["vm1"], self.mock_vms["vm2"],
                                                local1={"type": "nic", "nic": "lan_nic"},
                                                remote1={"type": "custom", "nic": "lan_nic"},
                                                peer1={"type": "dynip", "nic": "internet_nic"},
                                                auth=None)
        tunnel = self.vmnet.tunnels["vpn1"]

        self.assertEqual(tunnel.left_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.right_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.left_params['vpnconn_lan_type'], 'NIC')
        self.assertEqual(tunnel.right_params['vpnconn_lan_type'], 'NIC')
        self.assertEqual(tunnel.left_params['vpnconn_remote_type'], 'CUSTOM')
        self.assertEqual(tunnel.right_params['vpnconn_remote_type'], 'CUSTOM')
        self.assertEqual(tunnel.left_params['vpnconn_peer_type'], 'DYNIP')
        self.assertEqual(tunnel.right_params['vpnconn_peer_type'], 'IP')

    def test_configure_tunnel_between_vms_psk_basic(self):
        """Test a PSK tunnel setup and end-configuration between vms."""
        self._create_mock_vms()
        self.vmnet = VMNetwork(self.run_params, self.env)
        self.vmnet.configure_tunnel_between_vms("vpn1", self.mock_vms["vm1"], self.mock_vms["vm2"],
                                                local1={"type": "nic", "nic": "lan_nic"},
                                                remote1={"type": "custom", "nic": "lan_nic"},
                                                peer1={"type": "ip", "nic": "internet_nic"},
                                                auth={"type": "psk", "psk": "the secret",
                                                      "left_id": "arnold@vm1", "right_id": "arnold@vm2"})
        tunnel = self.vmnet.tunnels["vpn1"]

        self.assertEqual(tunnel.left_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.right_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.left_params['vpnconn_key_type'], 'PSK')
        self.assertEqual(tunnel.right_params['vpnconn_key_type'], 'PSK')
        self.assertEqual(tunnel.left_params['vpnconn_psk'], 'the secret')
        self.assertEqual(tunnel.right_params['vpnconn_psk'], 'the secret')
        self.assertEqual(tunnel.left_params['vpnconn_psk_own_id'], 'arnold@vm1')
        self.assertEqual(tunnel.right_params['vpnconn_psk_own_id'], 'arnold@vm2')
        self.assertEqual(tunnel.left_params['vpnconn_psk_own_id_type'], 'CUSTOM')
        self.assertEqual(tunnel.right_params['vpnconn_psk_own_id_type'], 'CUSTOM')
        self.assertEqual(tunnel.left_params['vpnconn_psk_foreign_id'], 'arnold@vm2')
        self.assertEqual(tunnel.right_params['vpnconn_psk_foreign_id'], 'arnold@vm1')
        self.assertEqual(tunnel.left_params['vpnconn_psk_foreign_id_type'], 'CUSTOM')
        self.assertEqual(tunnel.right_params['vpnconn_psk_foreign_id_type'], 'CUSTOM')

    def test_configure_tunnel_between_vms_psk_ip(self):
        """Test a PSK (IP type) tunnel setup and end-configuration between vms."""
        self._create_mock_vms()
        self.vmnet = VMNetwork(self.run_params, self.env)
        self.vmnet.configure_tunnel_between_vms("vpn1", self.mock_vms["vm1"], self.mock_vms["vm2"],
                                                local1={"type": "nic", "nic": "lan_nic"},
                                                remote1={"type": "custom", "nic": "lan_nic"},
                                                peer1={"type": "ip", "nic": "internet_nic"},
                                                auth={"type": "psk", "psk": "the secret",
                                                      "left_id": "", "right_id": ""})
        tunnel = self.vmnet.tunnels["vpn1"]

        self.assertEqual(tunnel.left_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.right_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.left_params['vpnconn_key_type'], 'PSK')
        self.assertEqual(tunnel.right_params['vpnconn_key_type'], 'PSK')
        self.assertEqual(tunnel.left_params['vpnconn_psk'], 'the secret')
        self.assertEqual(tunnel.right_params['vpnconn_psk'], 'the secret')
        self.assertEqual(tunnel.left_params['vpnconn_psk_own_id'], '')
        self.assertEqual(tunnel.right_params['vpnconn_psk_own_id'], '')
        self.assertEqual(tunnel.left_params['vpnconn_psk_own_id_type'], 'IP')
        self.assertEqual(tunnel.right_params['vpnconn_psk_own_id_type'], 'IP')
        self.assertEqual(tunnel.left_params['vpnconn_psk_foreign_id'], '')
        self.assertEqual(tunnel.right_params['vpnconn_psk_foreign_id'], '')
        self.assertEqual(tunnel.left_params['vpnconn_psk_foreign_id_type'], 'IP')
        self.assertEqual(tunnel.right_params['vpnconn_psk_foreign_id_type'], 'IP')

    def test_configure_tunnel_between_vms_pubkey(self):
        """Test a public key tunnel setup and end-configuration between vms."""
        self._create_mock_vms()
        self.vmnet = VMNetwork(self.run_params, self.env)
        try:
            self.vmnet.configure_tunnel_between_vms("vpn1", self.mock_vms["vm1"], self.mock_vms["vm2"],
                                                    local1={"type": "nic", "nic": "lan_nic"},
                                                    remote1={"type": "custom", "nic": "lan_nic"},
                                                    peer1={"type": "ip", "nic": "internet_nic"},
                                                    auth={"type": "pubkey"})
        except NotImplementedError:
            pass
        tunnel = self.vmnet.tunnels["vpn1"]

        self.assertEqual(tunnel.left_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.right_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel.left_params['vpnconn_key_type'], 'PUBLIC')
        self.assertEqual(tunnel.right_params['vpnconn_key_type'], 'PUBLIC')

        self.assertEqual(tunnel.left_params['vpnconn_own_key_name'], 'sample-key')
        self.assertEqual(tunnel.right_params['vpnconn_foreign_key_name'], 'sample-key')

    def test_configure_roadwarrior_vpn_on_server(self):
        """Test pure roadwarrior tunnel setup and end-configuration on the server."""
        self._create_mock_vms()
        self.run_params["ip_provider_b1_vm2"] = "10.2.0.1"
        self.vmnet = VMNetwork(self.run_params, self.env)
        try:
            self.vmnet.configure_roadwarrior_vpn_on_server("vpn1", self.mock_vms["vm1"], self.mock_vms["vm2"],
                                                           local1={"type": "nic", "nic": "lan_nic"},
                                                           remote1={"type": "modeconfig", "modeconfig_ip": "172.30.0.1"},
                                                           auth={"type": "pubkey"})
        except NotImplementedError:
            pass

    @mock.patch.object(vmnet.VMTunnel, 'configure_on_endpoint', mock.MagicMock())
    def test_configure_vpn_route(self):
        """Test tunnel routing setup among many vms."""
        self.run_params["vms"] += " vm3"
        self.run_params["ip_b1_vm3"] = "10.3.1.1"
        self.run_params["ip_b2_vm3"] = "172.19.1.1"

        self._create_mock_vms()
        self.vmnet = VMNetwork(self.run_params, self.env)
        self.vmnet.configure_tunnel_between_vms("vpn1", self.mock_vms["vm1"], self.mock_vms["vm2"],
                                                local1={"type": "nic", "nic": "lan_nic"},
                                                remote1={"type": "custom", "nic": "lan_nic"},
                                                peer1={"type": "ip", "nic": "internet_nic"},
                                                auth=None)
        tunnel1 = self.vmnet.tunnels["vpn1"]
        self.vmnet.configure_tunnel_between_vms("vpn2", self.mock_vms["vm2"], self.mock_vms["vm3"],
                                                local1={"type": "nic", "nic": "lan_nic"},
                                                remote1={"type": "custom", "nic": "lan_nic"},
                                                peer1={"type": "ip", "nic": "internet_nic"},
                                                auth=None)
        tunnel2 = self.vmnet.tunnels["vpn2"]

        self.vmnet.configure_vpn_route([self.mock_vms["vm1"], self.mock_vms["vm2"], self.mock_vms["vm3"]],
                                       ["vpn1", "vpn2"],
                                        remote1={"type": "custom", "nic": "lan_nic"},
                                        peer1={"type": "ip", "nic": "internet_nic"},
                                        auth=None)
        route1 = self.vmnet.tunnels["vpn1fwd"]
        route2 = self.vmnet.tunnels["vpn2fwd"]

        self.assertEqual(tunnel1.left_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel1.right_params['vpnconn'], 'vpn1')
        self.assertEqual(tunnel2.left_params['vpnconn'], 'vpn2')
        self.assertEqual(tunnel2.right_params['vpnconn'], 'vpn2')
        self.assertEqual(route1.left_params['vpnconn'], 'vpn1fwd')
        self.assertEqual(route1.right_params['vpnconn'], 'vpn1fwd')
        self.assertEqual(route2.right_params['vpnconn'], 'vpn2fwd')
        self.assertEqual(route2.right_params['vpnconn'], 'vpn2fwd')

        self.assertEqual(route1.left_params['vpnconn_lan_type'], 'CUSTOM')
        self.assertEqual(route1.right_params['vpnconn_lan_type'], 'CUSTOM')
        self.assertEqual(route2.left_params['vpnconn_lan_type'], 'CUSTOM')
        self.assertEqual(route2.right_params['vpnconn_lan_type'], 'CUSTOM')

        self.assertEqual(route1.left_params['vpnconn_remote_type'],
                         tunnel1.left_params['vpnconn_remote_type'])
        self.assertEqual(route1.right_params['vpnconn_remote_type'],
                         tunnel1.right_params['vpnconn_remote_type'])
        self.assertEqual(route1.left_params['vpnconn_peer_type'],
                         tunnel1.left_params['vpnconn_peer_type'])
        self.assertEqual(route1.right_params['vpnconn_peer_type'],
                         tunnel1.right_params['vpnconn_peer_type'])

        self.assertEqual(route2.left_params['vpnconn_remote_type'],
                         tunnel2.left_params['vpnconn_remote_type'])
        self.assertEqual(route2.right_params['vpnconn_remote_type'],
                         tunnel2.right_params['vpnconn_remote_type'])
        self.assertEqual(route2.left_params['vpnconn_peer_type'],
                         tunnel2.left_params['vpnconn_peer_type'])
        self.assertEqual(route2.right_params['vpnconn_peer_type'],
                         tunnel2.right_params['vpnconn_peer_type'])

        self.assertEqual(tunnel1.right_params['vpnconn_remote_net'], '172.17.0.0')
        self.assertEqual(tunnel2.left_params['vpnconn_remote_net'], '172.19.0.0')
        self.assertEqual(tunnel1.left_params['vpnconn_remote_net'], '172.18.0.0')
        self.assertEqual(route1.left_params['vpnconn_remote_net'], '172.19.0.0')
        self.assertEqual(route1.right_params['vpnconn_remote_net'],
                         tunnel1.right_params['vpnconn_remote_net'])
        self.assertEqual(route2.right_params['vpnconn_remote_net'], '172.17.0.0')
        self.assertEqual(tunnel2.right_params['vpnconn_remote_net'], '172.18.0.0')
        self.assertEqual(route2.left_params['vpnconn_remote_net'],
                         tunnel2.left_params['vpnconn_remote_net'])

        self.assertEqual(tunnel1.left_params['vpnconn_peer_ip'], '10.2.0.1')
        self.assertEqual(tunnel1.right_params['vpnconn_peer_ip'], '10.1.0.1')
        self.assertEqual(tunnel2.left_params['vpnconn_peer_ip'], '10.3.1.1')
        self.assertEqual(tunnel1.right_params['vpnconn_peer_ip'], '10.1.0.1')
        self.assertEqual(route1.left_params['vpnconn_peer_ip'],
                         tunnel1.left_params['vpnconn_peer_ip'])
        self.assertEqual(route1.right_params['vpnconn_peer_ip'],
                         tunnel1.right_params['vpnconn_peer_ip'])
        self.assertEqual(route2.left_params['vpnconn_peer_ip'],
                         tunnel2.left_params['vpnconn_peer_ip'])
        self.assertEqual(route2.right_params['vpnconn_peer_ip'],
                         tunnel2.right_params['vpnconn_peer_ip'])

        self.assertEqual(route1.left_params['vpnconn_activation'],
                         tunnel1.left_params['vpnconn_activation'])
        self.assertEqual(route1.right_params['vpnconn_activation'],
                         tunnel1.right_params['vpnconn_activation'])
        self.assertEqual(route2.left_params['vpnconn_activation'],
                         tunnel2.left_params['vpnconn_activation'])
        self.assertEqual(route2.right_params['vpnconn_activation'],
                         tunnel2.right_params['vpnconn_activation'])

    def test_connectivity_validate(self):
        """Test all connectivity testing methods of the vm network."""
        self.vmnet = VMNetwork(self.run_params, self.env)
        client, server = self.vmnet.get_vms()

        with self.assertRaises(exceptions.TestError):
            self.vmnet.ping(client, server)
        self.vmnet.reattach_interface(client, server)

        client.session.cmd_status_output.return_value = (0, "\n\n\n\n")
        self.vmnet.ping_validate(client, server)
        server.session.cmd_status_output.return_value = (0, "\n\n\n\n")
        self.vmnet.ping_all()

        client.session.cmd_status_output.return_value = (0, "")
        self.vmnet.http_connectivity(client, server)
        client.session.cmd_status_output.return_value = (0, "HTML")
        self.vmnet.http_connectivity_validate(client, server)
        client.session.cmd_status_output.return_value = (1, "")
        self.vmnet.http_connectivity_validate(client, server, require_blocked=True)
        client.session.cmd_status_output.return_value = (0, "HTML")
        self.vmnet.https_connectivity_validate(client, server)
        client.session.cmd_status_output.return_value = (1, "")
        self.vmnet.https_connectivity_validate(client, server, require_blocked=True)

        # TODO: have to make sure to update the gateway on reattaching
        self.run_params["ip_provider_b1_vm1"] = "172.18.0.1"
        self.vmnet = VMNetwork(self.run_params, self.env)
        self.vmnet.reattach_interface(client, server)
        client.session.cmd_status_output.return_value = (0, "")
        self.vmnet.ssh_connectivity(client, server)
        client.session.cmd_status_output.return_value = (0, "OpenSSH")
        self.vmnet.ssh_connectivity_validate(client, server)
        client.session.cmd_status_output.return_value = (1, "")
        self.vmnet.ssh_connectivity_validate(client, server, require_blocked=True)
        client.session.read_until_last_line_matches.return_value = (1, "vm2.net.lan")
        self.vmnet.ssh_hostname(client, server)
        client.session.read_until_last_line_matches.return_value = (1, "ETA 1s 100% done")
        self.vmnet.scp_files("file1", "file2", client, server)
        # HACK: let's pretend for a moment that the client is an ephemeral node
        self.vmnet.nodes[client.name]._ephemeral = True
        server.session.cmd.return_value = "host_name=vm1.net.lan"
        self.vmnet.ssh_hostname(server, client, dst_nic="internet_nic")
        self.vmnet.ssh_connectivity(server, client)
        self.vmnet.nodes[client.name]._ephemeral = False

        client.params["ftp_username"] = "totoro"
        client.params["ftp_password"] = "orotot"
        client.session.cmd_status_output.return_value = (0, "hi")
        self.vmnet.ftp_connectivity_validate("hi", "path", client, server)
        client.session.cmd_status_output.return_value = (0, "hi")
        self.vmnet.tftp_connectivity_validate("hi", "path", client, server)


if __name__ == '__main__':
    unittest.main()
