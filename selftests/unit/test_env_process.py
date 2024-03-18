import re
import sys

if sys.version_info[:2] == (2, 6):
    import unittest2 as unittest
else:
    import unittest

from virttest.env_process import QEMU_VERSION_RE


class QEMUVersion(unittest.TestCase):
    def test_regex(self):
        versions_expected = {
            "QEMU emulator version 2.9.0(qemu-kvm-rhev-2.9.0-16.el7_4.8)": (
                "2.9.0",
                "qemu-kvm-rhev-2.9.0-16.el7_4.8",
            ),
            "QEMU emulator version 2.10.50 (v2.10.0-594-gf75637badd)": (
                "2.10.50",
                "v2.10.0-594-gf75637badd",
            ),
            "QEMU emulator version 2.7.1(qemu-2.7.1-7.fc25), Copyright (c) "
            "2003-2016 Fabrice Bellard and the QEMU Project developers": (
                "2.7.1",
                "qemu-2.7.1-7.fc25",
            ),
            "QEMU PC emulator version 0.12.1 (qemu-kvm-0.12.1.2-2.503.el6_9.3),"
            " Copyright (c) 2003-2008 Fabrice Bellard": (
                "0.12.1",
                "qemu-kvm-0.12.1.2-2.503.el6_9.3",
            ),
        }
        for version, expected in list(versions_expected.items()):
            match = re.match(QEMU_VERSION_RE, version)
            self.assertEqual(match.groups(), expected)
