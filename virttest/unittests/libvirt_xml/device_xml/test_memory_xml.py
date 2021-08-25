import unittest

from virttest.libvirt_xml.devices import memory


XML = '''
    <memory access="private" discard="yes" model="dimm">
      <address base="0x120000000" slot="2" type="dimm"/>
      <alias name="dimm2"/>
      <source>
        <pagesize unit="KiB">4096</pagesize>
        <nodemask>1-3</nodemask>
        <path>/tmp/nvdimm</path>
      </source>
      <target>
        <size unit="KiB">524288</size>
        <node>0</node>
        <label>
          <size unit="KiB">128</size>
        </label>
      </target>
      <uuid>9066901e-c90a-46ad-8b55-c18868cf92ae</uuid>
    </memory>
    '''

dimm_device_attrs = {
    'address': {'type_name': 'dimm', 'attrs': {'type': 'dimm', 'slot': '2', 'base': '0x120000000'}},
    'alias': {'name': 'dimm2'},
    'mem_access': 'private',
    'mem_discard': 'yes',
    'mem_model': 'dimm',
    'source': {
        'pagesize': 4096,
        'pagesize_unit': 'KiB',
        'nodemask': '1-3',
        'path': '/tmp/nvdimm'
    },
    'target': {
        'size': 524288, 'size_unit': 'KiB', 'node': 0,
        'label': {'size': 128, 'size_unit': 'KiB'}
    },
    'uuid': '9066901e-c90a-46ad-8b55-c18868cf92ae',
}


class TestMemoryXML(unittest.TestCase):

    def test_setup_memory_default(self):
        dimm_device = memory.Memory()
        dimm_device.setup_attrs(**dimm_device_attrs)

        cmp_device = memory.Memory()
        cmp_device.xml = XML.strip()
        self.assertEqual(dimm_device, cmp_device)


if __name__ == '__main__':
    unittest.main()
