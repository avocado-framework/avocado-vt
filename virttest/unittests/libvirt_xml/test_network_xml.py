import unittest

from virttest.libvirt_xml import network_xml

# TODO: The current test doesn't cover all attributes of a network xml.
#  It needs update later
XML = """
    <network>
      <name>testnet</name>
      <forward mode='bridge'/>
      <bridge name='br0'/>
      <port isolated='yes'/>
      <ip address="192.168.122.1" netmask="255.255.255.0">
        <dhcp>
          <range start="192.168.122.2" end="192.168.122.254"/>
        </dhcp>
      </ip>
      <ip family="ipv6" address="2001:db8:ca2:2::1" prefix="64" netmask="255.255.255.0">
        <dhcp>
          <host name="paul" ip="2001:db8:ca2:2:3::1"/>
          <host id="0:1:0:1:18:aa:62:fe:0:16:3e:44:55:66" ip="2001:db8:ca2:2:3::2"/>
          <host id="0:3:0:1:0:16:3e:11:22:33" name="ralph" ip="2001:db8:ca2:2:3::3"/>
          <host id="0:4:7e:7d:f0:7d:a8:bc:c5:d2:13:32:11:ed:16:ea:84:63"
            name="badbob" ip="2001:db8:ca2:2:3::4"/>
        </dhcp>
      </ip>
    <portgroup name='engineering' default='yes'>
        <virtualport type='802.1Qbh'/>
        <bandwidth>
          <inbound average='1000' peak='5000' burst='5120'/>
          <outbound average='1000' peak='5000' burst='5120'/>
        </bandwidth>
      </portgroup>
      <portgroup name='sales' trustGuestRxFilters='no'>
        <virtualport type='802.1Qbh'/>
        <bandwidth>
          <inbound average='500' peak='2000' burst='2560'/>
          <outbound average='128' peak='256' burst='256'/>
        </bandwidth>
      </portgroup>
    </network>
"""

network_attrs = {
    "bridge": {"name": "br0"},
    "forward": {"mode": "bridge"},
    "ips": [
        {
            "address": "192.168.122.1",
            "dhcp_ranges": {
                "attrs": {"end": "192.168.122.254", "start": "192.168.122.2"}
            },
            "netmask": "255.255.255.0",
        },
        {
            "address": "2001:db8:ca2:2::1",
            "family": "ipv6",
            "hosts": [
                {"attrs": {"ip": "2001:db8:ca2:2:3::1", "name": "paul"}},
                {
                    "attrs": {
                        "id": "0:1:0:1:18:aa:62:fe:0:16:3e:44:55:66",
                        "ip": "2001:db8:ca2:2:3::2",
                    }
                },
                {
                    "attrs": {
                        "id": "0:3:0:1:0:16:3e:11:22:33",
                        "ip": "2001:db8:ca2:2:3::3",
                        "name": "ralph",
                    }
                },
                {
                    "attrs": {
                        "id": "0:4:7e:7d:f0:7d:a8:bc:c5:d2:13:32:11:ed:16:ea:84:63",
                        "ip": "2001:db8:ca2:2:3::4",
                        "name": "badbob",
                    }
                },
            ],
            "netmask": "255.255.255.0",
            "prefix": "64",
        },
    ],
    "name": "testnet",
    "port": {"isolated": "yes"},
    "portgroups": [
        {
            "bandwidth_inbound": {"average": "1000", "burst": "5120", "peak": "5000"},
            "bandwidth_outbound": {"average": "1000", "burst": "5120", "peak": "5000"},
            "default": "yes",
            "name": "engineering",
            "virtualport_type": "802.1Qbh",
        },
        {
            "bandwidth_inbound": {"average": "500", "burst": "2560", "peak": "2000"},
            "bandwidth_outbound": {"average": "128", "burst": "256", "peak": "256"},
            "name": "sales",
            "virtualport_type": "802.1Qbh",
        },
    ],
}


class TestNetworkXML(unittest.TestCase):
    def test_setup_network_default(self):
        network = network_xml.NetworkXML()
        network.setup_attrs(**network_attrs)

        cmp_device = network_xml.NetworkXML()
        cmp_device.xml = XML.strip()
        self.assertEqual(network, cmp_device)

    def test_fetch_attrs_network_default(self):
        network = network_xml.NetworkXML()
        network.xml = XML.strip()
        fetched_attrs = network.fetch_attrs()
        self.assertEqual(network_attrs, fetched_attrs)


if __name__ == "__main__":
    unittest.main()
