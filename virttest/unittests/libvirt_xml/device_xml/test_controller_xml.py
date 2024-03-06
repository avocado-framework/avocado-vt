import unittest

from virttest.libvirt_xml.devices import controller

XM_PCI = """
    <controller type='pci' index='1' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='1' port='0x10'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x0' multifunction='on'/>
    </controller>
    """

pci_controller_attrs = {
    "type_name": "pci",
    "index": "1",
    "model": "pcie-root-port",
    "model_name": {"name": "pcie-root-port"},
    "target": {"chassis": "1", "port": "0x10"},
    "address": {
        "type_name": "pci",
        "attrs": {
            "type": "pci",
            "domain": "0x0000",
            "bus": "0x00",
            "slot": "0x02",
            "function": "0x0",
            "multifunction": "on",
        },
    },
}


class TestcontrollerXML(unittest.TestCase):
    def test_setup_controller_pci(self):
        pci_ctrlr = controller.Controller()
        pci_ctrlr.setup_attrs(**pci_controller_attrs)

        cmp_device = controller.Controller()
        cmp_device.xml = XM_PCI.strip()
        self.assertEqual(pci_ctrlr, cmp_device)

    def test_fetch_attrs_controller_pci(self):
        pci_ctrlr = controller.Controller()
        pci_ctrlr.xml = XM_PCI.strip()
        fetched_attrs = pci_ctrlr.fetch_attrs()
        # 'type' is duplicated with 'type_name',
        #  the definition of Controller class should be modified
        fetched_attrs.pop("type")
        self.assertEqual(pci_controller_attrs, fetched_attrs)


if __name__ == "__main__":
    unittest.main()
