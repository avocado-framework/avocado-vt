import unittest

from virttest.libvirt_xml import vm_xml, xcepts

XML = """
<domain type='kvm'>
  <seclabel type='dynamic' model='selinux' relabel='yes'/>
  <seclabel type='dynamic' model='dac' relabel='yes'/>
</domain>
"""


def get_vmxml():
    vmxml = vm_xml.VMXML()
    vmxml['xml'] = XML.strip()

    return vmxml


class TestVMXMLDelSeclabel(unittest.TestCase):

    def test_del_seclabel_default(self):
        vmxml = get_vmxml()
        self.assertEqual(2, len(vmxml.get_seclabel()))
        vmxml.del_seclabel()
        with self.assertRaises(xcepts.LibvirtXMLError):
            vmxml.get_seclabel()

    def test_del_seclabel_with_conditions(self):
        vmxml = get_vmxml()
        del_dict = [('model', 'selinux'), ('relabel', 'yes')]
        self.assertEqual(2, len(vmxml.get_seclabel()))
        vmxml.del_seclabel(del_dict)
        seclabels = vmxml.get_seclabel()
        self.assertEqual(1, len(seclabels))
        self.assertEqual('dac', seclabels[0]['model'])

    def test_del_seclabel_with_partial_match(self):
        vmxml = get_vmxml()
        del_dict = [('model', 'selinux'), ('relabel', 'no')]
        self.assertEqual(2, len(vmxml.get_seclabel()))
        vmxml.del_seclabel(del_dict)
        seclabels = vmxml.get_seclabel()
        self.assertEqual(2, len(seclabels))


if __name__ == '__main__':
    unittest.main()
