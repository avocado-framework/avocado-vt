import unittest

from avocado import Test

from virttest.libvirt_xml import vm_xml, xcepts

XML = """
<domain type='kvm'>
  <seclabel type='dynamic' model='selinux' relabel='yes'/>
  <seclabel type='dynamic' model='dac' relabel='yes'/>
</domain>
"""


def get_vmxml():
    vmxml = vm_xml.VMXML()
    vmxml["xml"] = XML.strip()

    return vmxml


class TestVMXMLDelSeclabel(Test):
    def test_del_seclabel_default(self):
        vmxml = get_vmxml()
        self.assertEqual(2, len(vmxml.get_seclabel()))
        vmxml.del_seclabel()
        with self.assertRaises(xcepts.LibvirtXMLError):
            vmxml.get_seclabel()

    def test_del_seclabel_with_conditions(self):
        vmxml = get_vmxml()
        del_dict = [("model", "selinux"), ("relabel", "yes")]
        self.assertEqual(2, len(vmxml.get_seclabel()))
        vmxml.del_seclabel(del_dict)
        seclabels = vmxml.get_seclabel()
        self.assertEqual(1, len(seclabels))
        self.assertEqual("dac", seclabels[0]["model"])

    def test_del_seclabel_with_partial_match(self):
        vmxml = get_vmxml()
        del_dict = [("model", "selinux"), ("relabel", "no")]
        self.assertEqual(2, len(vmxml.get_seclabel()))
        vmxml.del_seclabel(del_dict)
        seclabels = vmxml.get_seclabel()
        self.assertEqual(2, len(seclabels))


IOMMUFD_XML = "<iommufd enabled='yes' fdgroup='iommu'/>"

iommufd_attrs = {
    "iommufd_attr": {"enabled": "yes", "fdgroup": "iommu"},
}


class TestVMXMLIommufd(Test):
    def test_setup_iommufd(self):
        iommufd = vm_xml.IOMMUFDXML()
        iommufd.setup_attrs(**iommufd_attrs)

        cmp_xml = vm_xml.IOMMUFDXML()
        cmp_xml.xml = IOMMUFD_XML
        self.assertEqual(iommufd, cmp_xml)
        self.assertNotIn("<attrs", str(iommufd))

    def test_fetch_attrs_iommufd(self):
        iommufd = vm_xml.IOMMUFDXML()
        iommufd.xml = IOMMUFD_XML
        self.assertEqual(iommufd_attrs, iommufd.fetch_attrs())

    def test_vmxml_iommufd_element(self):
        vmxml = vm_xml.VMXML()
        vmxml.xml = "<domain type='kvm'><name>test</name></domain>"
        iommufd = vm_xml.IOMMUFDXML()
        iommufd.setup_attrs(**iommufd_attrs)
        vmxml.iommufd = iommufd

        self.assertEqual(iommufd_attrs["iommufd_attr"], vmxml.iommufd.iommufd_attr)
        self.assertIn("<iommufd", str(vmxml))
        self.assertNotIn("<attrs", str(vmxml))

        del vmxml.iommufd
        with self.assertRaises(xcepts.LibvirtXMLError):
            _ = vmxml.iommufd


if __name__ == "__main__":
    unittest.main()
