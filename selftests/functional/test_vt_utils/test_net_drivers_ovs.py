import os
import subprocess
import sys
import unittest

from avocado.utils import path, process

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.isdir(os.path.join(basedir, "virttest")):
    sys.path.append(basedir)

from virttest.vt_utils.net.drivers import ovs


def ovs_vsctl_available():
    try:
        path.find_command("ovs-vsctl")
        return True
    except path.CmdNotFoundError:
        return False


def can_run_ovs_commands():
    try:
        process.run("ovs-vsctl show", ignore_status=False, shell=True)
        return True
    except process.CmdError:
        return False


class OvsTest(unittest.TestCase):

    def setUp(self):
        self.test_bridge = "test-br-aautils-func"
        if ovs_vsctl_available() and can_run_ovs_commands():
            try:
                ovs.del_ovs_bridge(self.test_bridge)
            except process.CmdError:
                pass

    def tearDown(self):
        if ovs_vsctl_available() and can_run_ovs_commands():
            try:
                ovs.del_ovs_bridge(self.test_bridge)
            except process.CmdError:
                pass

    @unittest.skipUnless(ovs_vsctl_available(), "ovs-vsctl command not available")
    @unittest.skipUnless(can_run_ovs_commands(), "Cannot run ovs-vsctl commands")
    def test_ovs_br_exists_false_for_nonexistent_bridge(self):
        # Ensure bridge doesn't exist
        self.assertFalse(ovs.ovs_br_exists("nonexistent-bridge-12345"))

    @unittest.skipUnless(ovs_vsctl_available(), "ovs-vsctl command not available")
    @unittest.skipUnless(can_run_ovs_commands(), "Cannot run ovs-vsctl commands")
    def test_bridge_lifecycle(self):
        self.assertFalse(ovs.ovs_br_exists(self.test_bridge))

        try:
            ovs.add_ovs_bridge(self.test_bridge)
            self.assertTrue(ovs.ovs_br_exists(self.test_bridge))
        except process.CmdError as e:
            self.skipTest(f"Cannot create OVS bridge: {e}")

        ovs.del_ovs_bridge(self.test_bridge)
        self.assertFalse(ovs.ovs_br_exists(self.test_bridge))

    def test_functions_without_ovs_installed(self):
        if ovs_vsctl_available():
            self.skipTest("OVS is available, skipping unavailability test")

        with self.assertRaises((process.CmdError, FileNotFoundError, OSError)):
            ovs.ovs_br_exists("test")

        with self.assertRaises((process.CmdError, FileNotFoundError, OSError)):
            ovs.add_ovs_bridge("test")

        with self.assertRaises((process.CmdError, FileNotFoundError, OSError)):
            ovs.del_ovs_bridge("test")


if __name__ == "__main__":
    unittest.main()
