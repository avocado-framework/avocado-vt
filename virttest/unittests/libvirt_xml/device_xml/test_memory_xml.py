import unittest

from virttest.libvirt_xml.devices import memory

test_xml_pairs = []

TESTXML_0 = """
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
    """

attrs_0 = {
    "address": {
        "type_name": "dimm",
        "attrs": {"type": "dimm", "slot": "2", "base": "0x120000000"},
    },
    "alias": {"name": "dimm2"},
    "mem_access": "private",
    "mem_discard": "yes",
    "mem_model": "dimm",
    "source": {
        "pagesize": 4096,
        "pagesize_unit": "KiB",
        "nodemask": "1-3",
        "path": "/tmp/nvdimm",
    },
    "target": {
        "size": 524288,
        "size_unit": "KiB",
        "node": 0,
        "label": {"size": 128, "size_unit": "KiB"},
    },
    "uuid": "9066901e-c90a-46ad-8b55-c18868cf92ae",
}

TESTXML_1 = """
  <memory model='dimm' access='private' discard='yes'>
    <target>
      <size unit='KiB'>524287</size>
      <node>0</node>
    </target>
  </memory>
"""

attrs_1 = {
    "mem_access": "private",
    "mem_discard": "yes",
    "mem_model": "dimm",
    "target": {"node": 0, "size": 524287, "size_unit": "KiB"},
}

TESTXML_2 = """
  <memory model='dimm'>
    <source>
      <pagesize unit='KiB'>2048</pagesize>
      <nodemask>1-3</nodemask>
    </source>
    <target>
      <size unit='KiB'>524287</size>
      <node>1</node>
    </target>
  </memory>
  """

attrs_2 = {
    "mem_model": "dimm",
    "source": {"nodemask": "1-3", "pagesize": 2048, "pagesize_unit": "KiB"},
    "target": {"node": 1, "size": 524287, "size_unit": "KiB"},
}

TESTXML_3 = """
  <memory model='nvdimm'>
    <uuid>9066901e-c90a-46ad-8b55-c18868cf92ae</uuid>
    <source>
      <path>/tmp/nvdimm</path>
    </source>
    <target>
      <size unit='KiB'>524288</size>
      <node>1</node>
      <label>
        <size unit='KiB'>128</size>
      </label>
      <readonly/>
    </target>
  </memory>
"""

attrs_3 = {
    "mem_model": "nvdimm",
    "source": {"path": "/tmp/nvdimm"},
    "target": {
        "label": {"size": 128, "size_unit": "KiB"},
        "node": 1,
        "readonly": True,
        "size": 524288,
        "size_unit": "KiB",
    },
    "uuid": "9066901e-c90a-46ad-8b55-c18868cf92ae",
}

TESTXML_4 = """
  <memory model='nvdimm' access='shared'>
    <uuid>e39080c8-7f99-4b12-9c43-d80014e977b8</uuid>
    <source>
      <path>/dev/dax0.0</path>
      <alignsize unit='KiB'>2048</alignsize>
      <pmem/>
    </source>
    <target>
      <size unit='KiB'>524288</size>
      <node>1</node>
      <label>
        <size unit='KiB'>128</size>
      </label>
    </target>
  </memory>
"""

attrs_4 = {
    "mem_access": "shared",
    "mem_model": "nvdimm",
    "source": {
        "alignsize": 2048,
        "alignsize_unit": "KiB",
        "path": "/dev/dax0.0",
        "pmem": True,
    },
    "target": {
        "label": {"size": 128, "size_unit": "KiB"},
        "node": 1,
        "size": 524288,
        "size_unit": "KiB",
    },
    "uuid": "e39080c8-7f99-4b12-9c43-d80014e977b8",
}

TESTXML_5 = """
  <memory model='virtio-pmem' access='shared'>
    <source>
      <path>/tmp/virtio_pmem</path>
    </source>
    <target>
      <size unit='KiB'>524288</size>
    </target>
  </memory>
"""

attrs_5 = {
    "mem_access": "shared",
    "mem_model": "virtio-pmem",
    "source": {"path": "/tmp/virtio_pmem"},
    "target": {"size": 524288, "size_unit": "KiB"},
}

TESTXML_6 = """
  <memory model='virtio-mem'>
    <source>
      <nodemask>1-3</nodemask>
      <pagesize unit='KiB'>2048</pagesize>
    </source>
    <target>
      <size unit='KiB'>2097152</size>
      <node>0</node>
      <block unit='KiB'>2048</block>
      <requested unit='KiB'>1048576</requested>
      <current unit='KiB'>524288</current>
    </target>
  </memory>
"""

attrs_6 = {
    "mem_model": "virtio-mem",
    "source": {"nodemask": "1-3", "pagesize": 2048, "pagesize_unit": "KiB"},
    "target": {
        "block_size": 2048,
        "block_unit": "KiB",
        "current_size": 524288,
        "current_unit": "KiB",
        "node": 0,
        "requested_size": 1048576,
        "requested_unit": "KiB",
        "size": 2097152,
        "size_unit": "KiB",
    },
}

groups = len([x for x in locals() if x.startswith("TESTXML_")])


class TestMemoryXML(unittest.TestCase):
    def test_setup_memory_default(self):
        for i in range(groups):
            print(i)
            mem_device = memory.Memory()
            mem_device.setup_attrs(**eval("attrs_" + str(i)))

            cmp_device = memory.Memory()
            cmp_device.xml = eval("TESTXML_" + str(i)).strip()
            self.assertEqual(mem_device, cmp_device)

    def test_fetch_attrs_memory_default(self):
        for i in range(groups):
            print(i)
            mem_device = memory.Memory()
            mem_device.xml = eval("TESTXML_" + str(i)).strip()
            self.assertEqual(eval("attrs_" + str(i)), mem_device.fetch_attrs())


if __name__ == "__main__":
    unittest.main()
