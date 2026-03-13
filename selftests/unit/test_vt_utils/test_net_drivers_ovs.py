import os
import sys
import unittest
import unittest.mock

from avocado.utils import process

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, "virttest")):
    sys.path.append(basedir)

from virttest.vt_utils.net.drivers import ovs


class OvsTest(unittest.TestCase):
    PATCH_PROCESS_RUN = "virttest.vt_utils.net.drivers.ovs.process.run"

    @unittest.mock.patch(PATCH_PROCESS_RUN)
    def test_ovs_br_exists_true(self, mock_run):
        mock_result = unittest.mock.MagicMock()
        mock_result.exit_status = 0
        mock_run.return_value = mock_result

        result = ovs.ovs_br_exists("br0")

        self.assertTrue(result)
        mock_run.assert_called_once_with("ovs-vsctl br-exists br0", shell=True)

    @unittest.mock.patch(PATCH_PROCESS_RUN)
    def test_ovs_br_exists_false(self, mock_run):
        mock_result = unittest.mock.MagicMock()
        mock_result.exit_status = 1
        mock_run.return_value = mock_result

        result = ovs.ovs_br_exists("nonexistent")

        self.assertFalse(result)
        mock_run.assert_called_once_with("ovs-vsctl br-exists nonexistent", shell=True)

    @unittest.mock.patch(PATCH_PROCESS_RUN)
    def test_add_ovs_bridge(self, mock_run):
        bridge_name = "test-bridge"

        ovs.add_ovs_bridge(bridge_name)

        expected_cmd = f"ovs-vsctl --may-exist add-br {bridge_name}"
        mock_run.assert_called_once_with(expected_cmd, shell=True)

    @unittest.mock.patch(PATCH_PROCESS_RUN)
    def test_del_ovs_bridge(self, mock_run):
        bridge_name = "test-bridge"

        ovs.del_ovs_bridge(bridge_name)

        expected_cmd = f"ovs-vsctl --if-exists del-br {bridge_name}"
        mock_run.assert_called_once_with(expected_cmd, shell=True)

    @unittest.mock.patch(PATCH_PROCESS_RUN)
    def test_ovs_br_exists_cmd_error(self, mock_run):
        mock_run.side_effect = process.CmdError(
            "ovs-vsctl br-exists test", None, "Command failed"
        )

        with self.assertRaises(process.CmdError):
            ovs.ovs_br_exists("test")

    @unittest.mock.patch(PATCH_PROCESS_RUN)
    def test_add_ovs_bridge_cmd_error(self, mock_run):
        mock_run.side_effect = process.CmdError(
            "ovs-vsctl --may-exist add-br test", None, "Command failed"
        )

        with self.assertRaises(process.CmdError):
            ovs.add_ovs_bridge("test")

    @unittest.mock.patch(PATCH_PROCESS_RUN)
    def test_del_ovs_bridge_cmd_error(self, mock_run):
        mock_run.side_effect = process.CmdError(
            "ovs-vsctl --if-exists del-br test", None, "Command failed"
        )

        with self.assertRaises(process.CmdError):
            ovs.del_ovs_bridge("test")


if __name__ == "__main__":
    unittest.main()
