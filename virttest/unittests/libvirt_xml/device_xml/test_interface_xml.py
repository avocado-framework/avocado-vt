import unittest

from virttest.libvirt_xml.devices import interface


XML = '''
  <interface type='network'>
    <source network='default' portgroup='engineering'/>
    <target dev='vnet7'/>
    <mac address="00:11:22:33:44:55"/>
    <ip family='ipv4' address='172.17.2.0' prefix='24'/>
    <ip family='ipv6' address='2001:db8:ac10:fd01::' prefix='64'/>
  </interface>
    '''

iface_attrs = {
    'type_name': 'network',
    'source': {'network': 'default', 'portgroup': 'engineering'},
    'target': {'dev': 'vnet7'},
    'mac_address': '00:11:22:33:44:55',
    'ips': [
        {'family': 'ipv4', 'address': '172.17.2.0', 'prefix': '24'},
        {'family': 'ipv6', 'address': '2001:db8:ac10:fd01::', 'prefix': '64'}
    ]
}


class TestcontrollerXML(unittest.TestCase):

    def test_setup_iface_default(self):
        iface = interface.Interface()
        iface.setup_attrs(**iface_attrs)

        cmp_device = interface.Interface()
        cmp_device.xml = XML.strip()
        self.assertEqual(iface, cmp_device)

    def test_fetch_attrs_iface_default(self):
        iface = interface.Interface()
        iface.xml = XML.strip()
        fetched_attrs = iface.fetch_attrs()
        self.assertEqual(iface_attrs, fetched_attrs)


if __name__ == '__main__':
    unittest.main()
