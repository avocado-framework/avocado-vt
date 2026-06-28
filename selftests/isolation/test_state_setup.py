#!/usr/bin/env python

import unittest
import unittest.mock as mock
import os
import types
import contextlib

from avocado import Test
from avocado.core import exceptions
from avocado.utils import process
from virttest import utils_params

import unittest_importer
# use old name to reduce amount of changes in the unit tests
from avocado_i2n.states import setup as ss
from avocado_i2n.states import qcow2
from avocado_i2n.states import lvm
from avocado_i2n.states import ramfile
from avocado_i2n.states import lxc
from avocado_i2n.states import btrfs
from avocado_i2n.states import pool
from avocado_i2n.states import vmnet


class MockDriver(unittest.TestCase):

    def __init__(self, params, mock_vms, mock_file_exists):
        super().__init__()

        self.state_backends = {"image": params["states_images"],
                               "vm": params["states_vms"],
                               "net": params["states_nets"]}

        self.mock_vms = mock_vms

        self.mock_file_exists = mock_file_exists
        self.mock_file_exists.side_effect = self._file_exists
        self.exist_switch = True
        self.exist_lambda = None

    def _file_exists(self, filepath):
        # avocado's test class does some unexpected monkey patching
        if filepath.endswith(".expected"):
            return False
        if self.exist_lambda:
            return self.exist_lambda(filepath)
        return self.exist_switch

    def _reset_extra_mocks(self):
        for vmname in self.mock_vms:
            self.mock_vms[vmname].reset_mock()
        self.mock_file_exists.reset_mock()
        self.exist_switch = True
        self.exist_lambda = None

    @contextlib.contextmanager
    def mock_show(self, state_names, state_type, root_exists=True):
        mock_driver = mock.MagicMock()
        self._reset_extra_mocks()
        backend = self.state_backends[state_type]
        if backend == "lvm":
            mock_driver.lv_check.return_value = root_exists
            mock_driver.lv_list.return_value = state_names
            with mock.patch('avocado_i2n.states.lvm.lv_utils', mock_driver):
                yield mock_driver
        elif backend in ["qcow2", "qcow2vt"]:
            if backend == "qcow2":
                self.mock_vms["vm1"].is_alive.return_value = False
                self.exist_switch = root_exists
            elif backend == "qcow2vt":
                self.exist_switch = True
                self.mock_vms["vm1"].is_alive.return_value = root_exists
            output = ""
            for state in state_names:
                size = "0 B" if state_type == "image" else "1 GiB"
                output += f"0         {state}         {size} 0000-00-00 00:00:00   00:00:00.000\n"
            mock_driver.return_value.snapshot_list.return_value = output
            with mock.patch('avocado_i2n.states.qcow2.QemuImg', mock_driver):
                yield mock_driver
        elif backend == "qcow2ext":
            self.mock_vms["vm1"].is_alive.return_value = False
            mock_driver.listdir.return_value = [s + ".qcow2" for s in state_names]
            mock_driver.stat.return_value.st_size = 0
            mock_driver.path.join = os.path.join
            mock_driver.path.dirname = os.path.dirname
            mock_driver.path.exists = self.mock_file_exists
            self.exist_switch = root_exists
            class QemuImgMock():
                def __init__(self, params, root_dir, tag):
                    self.image_filename = os.path.join(root_dir, tag)
            with mock.patch('avocado_i2n.states.qcow2.QemuImg', QemuImgMock):
                with mock.patch('avocado_i2n.states.qcow2.os', mock_driver):
                    yield mock_driver
        elif backend == "ramfile":
            ramfile.RamfileBackend.image_state_backend.show.return_value = state_names
            mock_driver.listdir.return_value = [s + ".state" for s in state_names]
            mock_driver.stat.return_value.st_size = 0
            mock_driver.path.join = os.path.join
            mock_driver.path.exists = self.mock_file_exists
            self.exist_switch = root_exists
            with mock.patch('avocado_i2n.states.ramfile.os', mock_driver):
                yield mock_driver
        else:
            raise ValueError(f"Unsupported backend for testing {backend}")

    def assert_show(self, mock_driver, _state_names, state_type):
        backend = self.state_backends[state_type]
        if backend == "lvm":
            mock_driver.lv_list.assert_called_once_with("disk_vm1")
        elif backend in ["qcow2", "qcow2vt"]:
            mock_driver.return_value.snapshot_list.assert_called_once_with(force_share=True)
        elif backend == "qcow2ext":
            mock_driver.listdir.assert_called_once_with("/images/vm1-abc.def/image1")
        elif backend == "ramfile":
            mock_driver.listdir.assert_called_once_with("/images/vm1-abc.def")
        else:
            raise ValueError(f"Unsupported backend for testing {backend}")

    def assert_get(self, mock_driver, state_name, state_type, action_type):
        backend = self.state_backends[state_type]
        if backend == "lvm":
            mock_driver.lv_check.assert_called_with("disk_vm1", "LogVol")
            if action_type == 1:
                mock_driver.lv_remove.assert_called_once_with('disk_vm1', 'current_state')
                mock_driver.lv_take_snapshot.assert_called_once_with('disk_vm1', state_name, 'current_state')
            else:
                mock_driver.lv_remove.assert_not_called()
                mock_driver.lv_take_snapshot.assert_not_called()
        elif backend in ["qcow2", "qcow2vt"]:
            driver_instance = mock_driver.return_value
            driver_instance.snapshot_list.assert_called_once_with(force_share=True)
            if action_type == 1 and state_type == "image":
                mock_driver.assert_called()
                second_creation_call_params = mock_driver.call_args_list[-2].args[0]
                self.assertEqual(second_creation_call_params["get_state"], state_name)
                driver_instance.snapshot_apply.assert_called_once_with()
            elif action_type == 1 and state_type == "vm":
                self.mock_vms["vm1"].loadvm.assert_called_once_with(state_name)
            elif state_type == "image":
                driver_instance.assert_not_called()
            else:
                self.mock_vms["vm1"].loadvm.assert_not_called()
        elif backend == "qcow2ext":
            # would have to mock a different dependency (QemuImg) here
            raise NotImplementedError("Not isolated backend - test via integration")
        elif backend == "ramfile":
            # TODO: cannot assert state_name as we need more isolated testing here
            mock_driver.listdir.assert_called_with(f"/images/vm1-abc.def")
            if action_type == 1:
                self.mock_vms["vm1"].restore_from_file.assert_called_once_with(f"/images/vm1-abc.def/{state_name}.state")
            else:
                self.mock_vms["vm1"].restore_from_file.assert_not_called()
        else:
            raise ValueError(f"Unsupported backend for testing {backend}")

    def assert_set(self, mock_driver, state_name, state_type, action_type):
        backend = self.state_backends[state_type]
        if backend == "lvm":
            if action_type == 1:
                mock_driver.lv_check.assert_called_with("disk_vm1", "LogVol")
                mock_driver.lv_remove.assert_not_called()
                mock_driver.lv_take_snapshot.assert_called_once_with('disk_vm1', 'current_state', state_name)
            elif action_type == 2:
                mock_driver.lv_check.assert_called_with("disk_vm1", "LogVol")
                mock_driver.lv_remove.assert_called_once_with('disk_vm1', state_name)
                mock_driver.lv_take_snapshot.assert_called_once_with('disk_vm1', 'current_state', state_name)
            else:
                mock_driver.lv_remove.assert_not_called()
                mock_driver.lv_take_snapshot.assert_not_called()
        elif backend in ["qcow2", "qcow2vt"]:
            mock_driver.return_value.snapshot_list.assert_called_once_with(force_share=True)
            if action_type == 1 and state_type == "image":
                mock_driver.assert_called()
                second_creation_call_params = mock_driver.call_args_list[-2].args[0]
                self.assertEqual(second_creation_call_params["set_state"], state_name)
                mock_driver.return_value.snapshot_create.assert_called_once_with()
            elif action_type == 2 and state_type == "image":
                mock_driver.assert_called()
                second_creation_call_params = mock_driver.call_args_list[-2].args[0]
                self.assertEqual(second_creation_call_params["set_state"], state_name)
                mock_driver.return_value.snapshot_del.assert_called_once_with()
                mock_driver.return_value.snapshot_create.assert_called_once_with()
            elif state_type == "image":
                mock_driver.return_value.assert_not_called()
            elif action_type in [1, 2] and state_type == "vm":
                self.mock_vms["vm1"].savevm.assert_called_once_with(state_name)
            else:
                self.mock_vms["vm1"].savevm.assert_not_called()
        elif backend == "qcow2ext":
            # would have to mock a different dependency (shutil.copy) here
            raise NotImplementedError("Not isolated backend - test via integration")
        elif backend == "ramfile":
            if action_type in [1, 2]:
                # TODO: cannot assert state_name as we need more isolated testing here
                mock_driver.listdir.assert_called_once_with(f"/images/vm1-abc.def")
                self.mock_vms["vm1"].save_to_file.assert_called_once_with(f"/images/vm1-abc.def/{state_name}.state")
            else:
                self.mock_vms["vm1"].save_to_file.assert_not_called()
        else:
            raise ValueError(f"Unsupported backend for testing {backend}")

    def assert_unset(self, mock_driver, state_name, state_type, action_type):
        backend = self.state_backends[state_type]
        if backend == "lvm":
            mock_driver.lv_check.assert_called_with("disk_vm1", "LogVol")
            if action_type == 1:
                mock_driver.lv_remove.assert_called_once_with("disk_vm1", state_name)
                mock_driver.lv_take_snapshot.assert_not_called()
            else:
                mock_driver.lv_remove.assert_not_called()
                mock_driver.lv_take_snapshot.assert_not_called()
        elif backend in ["qcow2", "qcow2vt"]:
            mock_driver.return_value.snapshot_list.assert_called_once_with(force_share=True)
            if action_type == 1 and state_type == "image":
                mock_driver.assert_called()
                second_creation_call_params = mock_driver.call_args_list[-2].args[0]
                self.assertEqual(second_creation_call_params["unset_state"], state_name)
                mock_driver.return_value.snapshot_del.assert_called_once_with()
            elif action_type == 1 and state_type == "vm":
                self.mock_vms["vm1"].monitor.send_args_cmd.assert_called_once_with(f'delvm id={state_name}')
            elif state_type == "image":
                mock_driver.return_value.assert_not_called()
            else:
                self.mock_vms["vm1"].monitor.send_args_cmd.assert_not_called()
        elif backend == "qcow2ext":
            # TODO: cannot assert state_name as we need more isolated testing here
            mock_driver.listdir.assert_called_once_with(f"/images/vm1-abc.def/image1")
            if action_type == 1:
                mock_driver.unlink.assert_called_once_with(f"/images/vm1-abc.def/image1/{state_name}.qcow2")
            else:
                mock_driver.unlink.assert_not_called()
        elif backend == "ramfile":
            # TODO: cannot assert state_name as we need more isolated testing here
            mock_driver.listdir.assert_called_once_with(f"/images/vm1-abc.def")
            if action_type == 1:
                mock_driver.unlink.assert_called_once_with(f"/images/vm1-abc.def/{state_name}.state")
            else:
                mock_driver.unlink.assert_not_called()
        else:
            raise ValueError(f"Unsupported backend for testing {backend}")


# TODO: keep these boundary tests until they are useful and the state backends
# they cover still supported, any newly introduced state backends should be
# covered by actual integration tests though (currently qcow2ext and some
# repeated but highly refurbished backends here)
@mock.patch('avocado_i2n.states.lvm.os.mkdir', mock.Mock(return_value=0))
@mock.patch('avocado_i2n.states.lvm.os.makedirs', mock.Mock(return_value=0))
@mock.patch('avocado_i2n.states.lvm.os.rmdir', mock.Mock(return_value=0))
@mock.patch('avocado_i2n.states.lvm.os.unlink', mock.Mock(return_value=0))
@mock.patch('avocado_i2n.states.lvm.shutil.rmtree', mock.Mock(return_value=0))
class StatesBoundaryTest(Test):

    def setUp(self):
        self.run_str = ""

        ss.BACKENDS = {"qcow2": qcow2.QCOW2Backend, "qcow2ext": qcow2.QCOW2ExtBackend,
                       "lvm": lvm.LVMBackend,
                       "lxc": lxc.LXCBackend, "btrfs": btrfs.BtrfsBackend,
                       "qcow2vt": qcow2.QCOW2VTBackend, "ramfile": ramfile.RamfileBackend,
                       "vmnet": vmnet.VMNetBackend,
                       "mock": mock.MagicMock(spec=ss.StateBackend)}
        ramfile.RamfileBackend.image_state_backend = mock.MagicMock()

        self.run_params = utils_params.Params()
        self.run_params["nets"] = "net1"
        self.run_params["vms"] = "vm1"
        self.run_params["images"] = "image1"
        self.run_params["main_vm"] = "vm1"
        self.run_params["image_name_vm1"] = "image"
        self.run_params["vms_base_dir"] = "/images"
        self.run_params["images_base_dir_vm1"] = "/images/vm1"
        self.run_params["nets"] = "net1"
        self.run_params["states_chain"] = "nets vms images"
        self.run_params["states_nets"] = "mock"
        self.run_params["states_images"] = "mock"
        self.run_params["states_vms"] = "mock"
        self.run_params["check_mode"] = "rr"
        self.run_params["nets_gateway"] = ""
        self.run_params["nets_host"] = ""
        self.run_params["pool_scope"] = "own"

        self.env = mock.MagicMock(name='env')
        self.env.get_vm = mock.MagicMock(side_effect=self._get_mock_vm)

        self.mock_vms = {}
        self.driver = None

        self.mock_file_exists = mock.MagicMock()
        # TODO: qcow2 is still needed for LVM root setting and too many tests
        exists_patch = mock.patch('avocado_i2n.states.qcow2.os.path.exists',
                                  self.mock_file_exists)
        exists_patch.start()
        self.addCleanup(exists_patch.stop)

    def _set_image_lvm_params(self):
        self.run_params["states_images"] = "lvm"
        self.run_params["vg_name_vm1"] = "disk_vm1"
        self.run_params["lv_name"] = "LogVol"
        self.run_params["lv_pointer_name"] = "current_state"

    def _set_image_qcow2_params(self):
        self.run_params["states_images"] = "qcow2"
        self.run_params["image_format"] = "qcow2"
        self.run_params["qemu_img_binary"] = "qemu-img"

    def _set_image_qcow2ext_params(self):
        self.run_params["states_images"] = "qcow2ext"
        self.run_params["image_format"] = "qcow2"
        self.run_params["qemu_img_binary"] = "qemu-img"
        self.run_params["swarm_pool"] = "/images"
        self.run_params["object_id"] = "vm1-abc.def"

    def _set_vm_qcow2_params(self):
        self.run_params["states_vms"] = "qcow2vt"
        self.run_params["image_format"] = "qcow2"
        self.run_params["qemu_img_binary"] = "qemu-img"

    def _set_vm_ramfile_params(self):
        self.run_params["states_vms"] = "ramfile"
        self.run_params["swarm_pool"] = "/images"
        self.run_params["object_id"] = "vm1-abc.def"

    def _get_mock_vm(self, vm_name):
        return self.mock_vms[vm_name]

    def _create_mock_vms(self):
        for vm_name in self.run_params.objects("vms"):
            self.mock_vms[vm_name] = mock.MagicMock(name=vm_name)
            self.mock_vms[vm_name].name = vm_name
            self.mock_vms[vm_name].params = self.run_params.object_params(vm_name)

    def _create_mock_driver(self):
        self.driver = MockDriver(self.run_params,
                                 self.mock_vms, self.mock_file_exists)

    def _prepare_driver_from_backend(self, backend):
        self._create_mock_vms()

        if backend in ["qcow2", "qcow2ext", "lvm"]:
            backend_type = "image"
            self.run_params["skip_types"] = "nets nets/vms"
        elif backend in ["vmnet", "lxc", "btrfs"]:
            backend_type = "net"
            self.run_params["skip_types"] = "nets/vms nets/vms/images"
        else:
            backend_type = "vm"
            self.run_params["skip_types"] = "nets nets/vms/images"
        if backend == "qcow2":
            self._set_image_qcow2_params()
        elif backend == "qcow2ext":
            self._set_image_qcow2ext_params()
        elif backend == "lvm":
            self._set_image_lvm_params()
        elif backend == "qcow2vt":
            self._set_vm_qcow2_params()
        elif backend == "ramfile":
            self._set_vm_ramfile_params()
        self._create_mock_driver()

        return backend_type

    def _test_show_states(self, backend):
        backend_type = self._prepare_driver_from_backend(backend)

        # assert empty list without available states
        with self.driver.mock_show([], backend_type) as driver:
            states = ss.show_states(self.run_params, self.env)
            self.driver.assert_show(driver, [], backend_type)
        self.assertEqual(len(states), 0)

        # assert nonempty list with available states
        with self.driver.mock_show(["launch", "launch_2-0", "launch3.0"], backend_type) as driver:
            states = ss.show_states(self.run_params, self.env)
            self.driver.assert_show(driver, ["launch", "launch_2-0", "launch3.0"], backend_type)
        self.assertEqual(len(states), 3)
        self.assertIn("launch", states)
        self.assertIn("launch_2-0", states)
        self.assertIn("launch3.0", states)
        self.assertNotIn("root", states)
        self.assertNotIn("boot", states)

    def _test_get_state(self, backend):
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"get_state_{backend_type}s_vm1"] = "launch"

        # assert state is retrieved if available after it was checked
        with self.driver.mock_show(["launch"], backend_type) as driver:
            ss.get_states(self.run_params, self.env)
            self.driver.assert_get(driver, "launch", backend_type, 1)

        # assert state is not retrieved if not available after it was checked
        with self.driver.mock_show([], backend_type) as driver:
            ss.get_states(self.run_params, self.env)
            self.driver.assert_get(driver, "launch", backend_type, 0)

    def _test_set_state(self, backend):
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"set_state_{backend_type}s_vm1"] = "launch"

        # assert state is removed and saved if available after it was checked
        with self.driver.mock_show(["launch"], backend_type) as driver:
            ss.set_states(self.run_params, self.env)
            self.driver.assert_set(driver, "launch", backend_type, 2)

        # assert state is saved if not available after it was checked
        with self.driver.mock_show([], backend_type) as driver:
            ss.set_states(self.run_params, self.env)
            self.driver.assert_set(driver, "launch", backend_type, 1)

    def _test_unset_state(self, backend):
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"unset_state_{backend_type}s_vm1"] = "launch"

        # assert state is removed if available after it was checked
        with self.driver.mock_show(["launch"], backend_type) as driver:
            ss.unset_states(self.run_params, self.env)
            self.driver.assert_unset(driver, "launch", backend_type, 1)

        # assert state is not removed if not available after it was checked
        with self.driver.mock_show([], backend_type) as driver:
            ss.unset_states(self.run_params, self.env)
            self.driver.assert_unset(driver, "launch", backend_type, 0)

    def test_show_image_lvm(self):
        """Test that state listing with the LVM backend works correctly."""
        self._test_show_states("lvm")

    def test_show_image_qcow2(self):
        """Test that state listing with the QCOW2 internal state backend works correctly."""
        self._test_show_states("qcow2")

    def test_show_image_qcow2ext(self):
        """Test that state listing with the QCOW2 external state backend works correctly."""
        self._test_show_states("qcow2ext")

    def test_show_image_qcow2ext_swarm(self):
        """Test that state listing with the QCOW2 external state prioritizes swarm pool."""
        backend = "qcow2ext"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params["swarm_pool"] = "/some/swarm2"
        with self.driver.mock_show(["launch"], backend_type) as driver:
            states = ss.show_states(self.run_params, self.env)
            driver.listdir.assert_called_once_with("/some/swarm2/vm1-abc.def/image1")
        self.assertEqual(len(states), 1)

    def test_show_vm_qcow2(self):
        """Test that state listing with the QCOW2VT backend works correctly."""
        self._test_show_states("qcow2vt")

    def test_show_vm_ramfile(self):
        """Test that state listing with the ramfile backend works correctly."""
        self._test_show_states("ramfile")

    def test_show_vm_ramfile_swarm(self):
        """Test that state listing with the ramfile external state prioritizes swarm pool."""
        backend = "ramfile"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params["swarm_pool"] = "/some/swarm2"
        with self.driver.mock_show(["launch"], backend_type) as driver:
            states = ss.show_states(self.run_params, self.env)
            driver.listdir.assert_called_once_with("/some/swarm2/vm1-abc.def")
        self.assertEqual(len(states), 1)

    def test_show_image_qcow2_boot(self):
        """
        Test that state checking with the QCOW2 backend considers running vms.

        .. todo:: Consider whether this is a good approach to spread to other
            state backends or rid ourselves of the QCOW2(VT) hacks altogether.
        """
        backend = "qcow2"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"check_state_{backend_type}s_vm1"] = "launch"

        # assert behavior on root and state availability
        with self.driver.mock_show(["launch"], backend_type, True) as driver:
            self.mock_vms["vm1"].is_alive.return_value = True
            exists = ss.check_states(self.run_params, self.env)
            # TODO: define more action types to achieve backend independence here,
            # perhaps after we generalize run vm requirement to all backend roots
            #self.driver.assert_check(driver, "launch", backend_type, 2)
            # assert root state is checked as a prerequisite
            # assert off switch as part of root state is checked as a prerequisite
            self.mock_vms["vm1"].is_alive.assert_called()
            self.mock_file_exists.assert_not_called()
            # assert actual state is not checked and not available
            driver.system_output.assert_not_called()
        self.assertFalse(exists)

    def test_check_vm_qcow2_noimage(self):
        """
        Test that state checking with the QCOW2VT backend considers missing images.

        .. todo:: Consider whether this is a good approach to spread to other
            state backends or rid ourselves of the QCOW2(VT) hacks altogether.
        """
        backend = "qcow2vt"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"check_state_{backend_type}s_vm1"] = "launch"

        with self.driver.mock_show(["launch"], backend_type, True) as driver:
            self.driver.exist_switch = False
            exists = ss.check_states(self.run_params, self.env)
            # TODO: define more action types to achieve backend independence here,
            # perhaps after we generalize run vm requirement to all backend roots
            #self.driver.assert_check(driver, "launch", backend_type, 2)
            # assert root state is checked as a prerequisite
            # assert missing image as part of root state is checked as a prerequisite
            self.mock_file_exists.assert_called_once_with("/images/vm1/image.qcow2")
            self.mock_vms["vm1"].is_alive.assert_not_called()
            # assert actual state is not checked and not available
            driver.system_output.assert_not_called()
        self.assertFalse(exists)

    def test_get_image_lvm(self):
        """Test that state getting with the LVM backend works with available root."""
        # use a nondefault policy that doesn't raise any errors here
        self.run_params["get_mode_vm1"] = "ri"
        self._test_get_state("lvm")

    def test_get_image_qcow2(self):
        """Test that state getting with the QCOW2 backend works with available root."""
        # use a nondefault policy that doesn't raise any errors here
        self.run_params["get_mode_vm1"] = "ri"
        self._test_get_state("qcow2")

    def test_get_vm_qcow2(self):
        """Test that state getting with the QCOW2VT backend works with available root."""
        # use a nondefault policy that doesn't raise any errors here
        self.run_params["get_mode_vm1"] = "ri"
        self._test_get_state("qcow2vt")

    def test_get_vm_ramfile(self):
        """Test that state getting with the ramdisk backend works with available root."""
        # use a nondefault policy that doesn't raise any errors here
        self.run_params["get_mode_vm1"] = "ri"
        self._test_get_state("ramfile")

    def test_set_image_lvm(self):
        """Test that state setting with the LVM backend works with available root."""
        self._test_set_state("lvm")

    def test_set_image_qcow2(self):
        """Test that state setting with the QCOW2 backend works with available root."""
        self._test_set_state("qcow2")

    def test_set_vm_qcow2(self):
        """Test that state setting with the QCOW2VT backend works with available root."""
        self._test_set_state("qcow2vt")

    def test_set_vm_ramfile(self):
        """Test that state setting with the ramfile backend works with available root."""
        self._test_set_state("ramfile")

    def test_unset_image_lvm(self):
        """Test that state unsetting with the LVM backend works with available root."""
        self._test_unset_state("lvm")

    def test_unset_image_qcow2(self):
        """Test that state unsetting with the QCOW2 internal state backend works with available root."""
        self._test_unset_state("qcow2")

    def test_unset_image_qcow2ext(self):
        """Test that state unsetting with the QCOW2 external state backend works with available root."""
        self._test_unset_state("qcow2ext")

    def test_unset_vm_qcow2(self):
        """Test that state unsetting with the QCOW2VT backend works with available root."""
        self._test_unset_state("qcow2vt")

    def test_unset_vm_ramfile(self):
        """Test that state unsetting with the ramfile backend works with available root."""
        self._test_unset_state("ramfile")

    def test_unset_image_lvm_keep_pointer(self):
        """Test that LVM backend's pointer state cannot be unset."""
        backend = "lvm"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params["unset_state_images_vm1"] = "current_state"

        with self.driver.mock_show(["current_state", "launch"], backend_type, True) as driver:
            with self.assertRaises(ValueError):
                ss.unset_states(self.run_params, self.env)
            self.driver.assert_unset(driver, "current_state", backend_type, 0)

    def test_check_root_image_lvm(self):
        """Test that root checking with the LVM backend works."""
        backend = "lvm"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"check_state_{backend_type}s_vm1"] = "root"

        # assert root state is correctly detected
        with self.driver.mock_show([], backend_type, True) as driver:
            exists = ss.check_states(self.run_params, self.env)
            driver.lv_check.assert_called_once_with("disk_vm1", "LogVol")
        self.assertTrue(exists)

        # assert root state is correctly not detected
        with self.driver.mock_show([], backend_type, False) as driver:
            exists = ss.check_states(self.run_params, self.env)
            driver.lv_check.assert_called_once_with("disk_vm1", "LogVol")
        self.assertFalse(exists)

    def test_check_root_image_qcow2(self):
        """Test that root checking with the QCOW2 backend works."""
        backend = "qcow2"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"check_state_{backend_type}s_vm1"] = "root"
        # bonus: test for two images rather than one
        self.run_params["images_vm1"] = "image1 image2"
        self.run_params["image_name_image1_vm1"] = "vm1/image1"
        self.run_params["image_name_image2_vm1"] = "vm1/image2"

        # assert root state is correctly detected
        with self.driver.mock_show([], backend_type, True) as driver:
            exists = ss.check_states(self.run_params, self.env)
        self.assertTrue(exists)

        # assert root state is correctly not detected
        with self.driver.mock_show([], backend_type, False) as driver:
            exists = ss.check_states(self.run_params, self.env)
        self.assertFalse(exists)

        # assert running vms result in not completely available root state
        with self.driver.mock_show([], backend_type, True) as driver:
            self.mock_vms["vm1"].is_alive.return_value = True
            exists = ss.check_states(self.run_params, self.env)
        self.assertFalse(exists)

    def test_check_root_vm_qcow2(self):
        """Test that root checking with the QCOW2VT backend works."""
        backend = "qcow2vt"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"check_state_{backend_type}s_vm1"] = "root"

        # assert root state is correctly detected
        with self.driver.mock_show([], backend_type, True) as driver:
            exists = ss.check_states(self.run_params, self.env)
            self.mock_vms["vm1"].is_alive.assert_called_once_with()
        self.assertTrue(exists)

        # assert root state is correctly not detected
        with self.driver.mock_show([], backend_type, False) as driver:
            exists = ss.check_states(self.run_params, self.env)
            self.mock_vms["vm1"].is_alive.assert_called_once_with()
        self.assertFalse(exists)

    def test_check_root_vm_ramfile(self):
        """Test that root checking with the ramfile backend works."""
        backend = "ramfile"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"check_state_{backend_type}s_vm1"] = "root"
        # bonus: test for two images rather than one
        self.run_params["images_vm1"] = "image1 image2"
        self.run_params["image_name_image1_vm1"] = "vm1/image1"
        self.run_params["image_name_image2_vm1"] = "vm1/image2"

        # assert root state is correctly detected
        for image_format in ["qcow2", "raw", "something-else"]:
            with self.subTest(f"Test root checking with ramfile using image format {image_format}"):
                self.run_params["image_format"] = image_format
                with self.driver.mock_show([], backend_type, True) as driver:
                    file_suffix = f".{image_format}" if image_format != "raw" else ""
                    self.driver.exist_lambda = lambda filename: filename.endswith(file_suffix) or filename.endswith("vm1-abc.def")
                    exists = ss.check_states(self.run_params, self.env)
                self.assertTrue(exists)

        # assert root state is correctly not detected
        with self.driver.mock_show([], backend_type, False) as driver:
            exists = ss.check_states(self.run_params, self.env)
        self.assertFalse(exists)

    def test_get_root(self):
        """Test that root getting with a state backend works."""
        # only test with most default backends
        for backend in ss.BACKENDS:
            with self.subTest(f"Testing get root for backend {backend}"):
                # TODO: not fully isolated backends
                if backend in ["qcow2ext"]:
                    continue
                # TODO: net-based not fulyl isolated backends
                if backend in ["lxc", "btrfs", "vmnet"]:
                    continue
                backend_type = self._prepare_driver_from_backend(backend)
                self.run_params[f"get_state_{backend_type}s_vm1"] = "root"

                # cannot verify that the operation is NOOP so simply run it for coverage
                with self.driver.mock_show([], backend_type, True) as driver:
                    ss.get_states(self.run_params, self.env)

    @mock.patch('avocado_i2n.states.lvm.env_process', mock.Mock(return_value=0))
    @mock.patch('avocado_i2n.states.lvm.process')
    def test_set_root_image_lvm(self, mock_process):
        """Test that root setting with the LVM backend works."""
        backend = "lvm"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"set_state_{backend_type}s_vm1"] = "root"
        self.run_params["set_size_vm1"] = "30G"
        self.run_params["lv_pool_name"] = "thin_pool"
        self.run_params["lv_pool_size"] = "30G"
        self.run_params["lv_size"] = "30G"
        self.run_params["image_name_vm1"] = "vm1/image"
        self.run_params["disk_sparse_filename_vm1"] = "virtual_hdd_vm1"
        self.run_params["use_tmpfs"] = "yes"
        self.run_params["disk_basedir_vm1"] = "/tmp"
        self.run_params["disk_vg_size_vm1"] = "40000"
        self.run_params["image_raw_device_vm1"] = "no"
        # TODO: LVM is still internally tied to QCOW images and needs testing otherwise
        self.run_params["image_format"] = "qcow2"

        def process_run_side_effect(cmd, **kwargs):
            if cmd == "pvs":
                stdout = b"/dev/loop0 disk_vm1   lvm2"
            elif cmd == "losetup --find":
                stdout = b"/dev/loop0"
            elif cmd == "losetup --all":
                stdout = b"/dev/loop0: [0050]:2033 (/tmp/vm1_image1/virtual_hdd)"
            else:
                stdout = b""
            result = process.CmdResult(cmd, stdout=stdout, exit_status=0)
            return result
        mock_process.run.side_effect = process_run_side_effect
        mock_process.system.return_value = 0

        # assert root state is detected and overwritten
        mock_process.reset_mock()
        with self.driver.mock_show([], backend_type, True) as driver:
            ss.set_states(self.run_params, self.env)
            driver.lv_check.assert_called_with('disk_vm1', 'LogVol')
            driver.lv_create.assert_called_once_with('disk_vm1', 'LogVol', '30G', pool_name='thin_pool', pool_size='30G')
            driver.lv_take_snapshot.assert_called_once_with('disk_vm1', 'LogVol', 'current_state')
        mock_process.run.assert_called_with('vgcreate disk_vm1 /dev/loop0', sudo=True)

        # assert root state is not detected and created
        mock_process.reset_mock()
        with self.driver.mock_show([], backend_type, True) as driver:
            ss.set_states(self.run_params, self.env)
            driver.lv_check.assert_called_with('disk_vm1', 'LogVol')
            driver.lv_create.assert_called_once_with('disk_vm1', 'LogVol', '30G', pool_name='thin_pool', pool_size='30G')
            driver.lv_take_snapshot.assert_called_once_with('disk_vm1', 'LogVol', 'current_state')
        mock_process.run.assert_called_with('vgcreate disk_vm1 /dev/loop0', sudo=True)

    @mock.patch('avocado_i2n.states.qcow2.env_process')
    def test_set_root_image_qcow2(self, mock_env_process):
        """Test that root setting with the QCOW2 backend works."""
        backend = "qcow2"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"set_state_{backend_type}s_vm1"] = "root"

        # assert root state is detected and overwritten
        mock_env_process.reset_mock()
        with self.driver.mock_show([], backend_type, True) as driver:
            exists_times = [True, False]
            self.driver.exist_lambda = lambda filename: exists_times.pop(0)
            ss.set_states(self.run_params, self.env)
            self.mock_vms["vm1"].is_alive.assert_called()
            # called twice because QCOW2's set_root can only set missing root part
            # like only turning off the vm or only creating an image
            self.mock_file_exists.assert_called_with("/images/vm1/image.qcow2")
        mock_env_process.preprocess_image.assert_called_once()

        # assert root state is not detected and created
        mock_env_process.reset_mock()
        with self.driver.mock_show([], backend_type, False) as driver:
            ss.set_states(self.run_params, self.env)
            self.mock_vms["vm1"].is_alive.assert_called()
            # called twice because QCOW2's set_root can only set missing root part
            # like only turning off the vm or only creating an image
            self.mock_file_exists.assert_called_with("/images/vm1/image.qcow2")
        mock_env_process.preprocess_image.assert_called_once()

        # assert running vms result in setting only remaining part of root state
        mock_env_process.reset_mock()
        with self.driver.mock_show([], backend_type, True) as driver:
            self.mock_vms["vm1"].is_alive.return_value = True
            ss.set_states(self.run_params, self.env)
            # is vm is not alive root is not available and no need to check image existence
            self.mock_vms["vm1"].is_alive.assert_called()
            self.mock_vms["vm1"].destroy.assert_called_once_with(gracefully=True)
        mock_env_process.preprocess_image.assert_not_called()

    @mock.patch('avocado_i2n.states.ramfile.env_process')
    @mock.patch('avocado_i2n.states.qcow2.env_process')
    def test_set_root_vm(self, _mock_env1, _mock_env2):
        """Test that root setting with a vm state backend works."""
        for backend in ["qcow2vt", "ramfile"]:
            with self.subTest(f"Testing set root for backend {backend}"):
                backend_type = self._prepare_driver_from_backend(backend)
                self.run_params[f"set_state_{backend_type}s_vm1"] = "root"

                # TODO: there are now way too many conditions in each root state and only
                # some of them are mocked for this test to have a proper coverage and definitions

                # assert root state is not detected and created
                with self.driver.mock_show([], backend_type, False) as driver:
                    ss.set_states(self.run_params, self.env)
                    if backend == "qcow2vt":
                        self.mock_vms["vm1"].create.assert_called_once_with()
                    elif backend == "ramfile":
                        driver.makedirs.assert_called_once_with("/images/vm1-abc.def", exist_ok=True)

                # assert root state is detected and but not overwritten in this case
                with self.driver.mock_show([], backend_type, True) as driver:
                    ss.set_states(self.run_params, self.env)
                    self.mock_vms["vm1"].create.assert_not_called()
                    if backend == "ramfile":
                        driver.makedirs.assert_called_once_with("/images/vm1-abc.def", exist_ok=True)

    @mock.patch('avocado_i2n.states.lvm.vg_cleanup')
    def test_unset_root_image_lvm(self, mock_vg_cleanup):
        """Test that root unsetting with the LVM backend works."""
        backend = "lvm"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"unset_state_{backend_type}s_vm1"] = "root"
        self.run_params["image_name_vm1"] = "vm1/image"
        self.run_params["disk_sparse_filename_vm1"] = "virtual_hdd_vm1"
        self.run_params["use_tmpfs"] = "yes"
        self.run_params["disk_basedir_vm1"] = "/tmp"
        self.run_params["image_raw_device_vm1"] = "no"

        # assert root state is detected and removed
        mock_vg_cleanup.reset_mock()
        with self.driver.mock_show([], backend_type, True) as driver:
            ss.unset_states(self.run_params, self.env)
            driver.vg_check.assert_called_once_with('disk_vm1')
        mock_vg_cleanup.assert_called_once_with('virtual_hdd_vm1', '/tmp/disk_vm1', 'disk_vm1', None, True)

        # test tolerance to cleanup errors
        mock_vg_cleanup.reset_mock()
        mock_vg_cleanup.side_effect = exceptions.TestError("cleanup failed")
        with self.driver.mock_show([], backend_type, True) as driver:
            driver.vg_check.return_value = True
            ss.unset_states(self.run_params, self.env)
            driver.vg_check.assert_called_once_with('disk_vm1')
        mock_vg_cleanup.assert_called_once_with('virtual_hdd_vm1', '/tmp/disk_vm1', 'disk_vm1', None, True)

    @mock.patch('avocado_i2n.states.qcow2.os')
    @mock.patch('avocado_i2n.states.qcow2.env_process')
    def test_unset_root_image_qcow2(self, mock_env_process, mock_os):
        """Test that root unsetting with the QCOW2 backend works."""
        backend = "qcow2"
        backend_type = self._prepare_driver_from_backend(backend)
        self.run_params[f"unset_state_{backend_type}s_vm1"] = "root"

        # assert root state is detected and removed
        mock_os.reset_mock()
        mock_env_process.reset_mock()
        with self.driver.mock_show([], backend_type, True) as driver:
            ss.unset_states(self.run_params, self.env)
        mock_env_process.postprocess_image.assert_called_once()
        mock_os.rmdir.assert_called_once()

        # TODO: assert running vms result in not completely available root state
        # TODO: running vm implies no root state which implies ignore or abort policy
        #self.mock_vms["vm1"].destroy.assert_called_once_with(gracefully=False)
        pass

    def test_unset_root_vm(self):
        """Test that root unsetting with a vm state backend works."""
        for backend in ["qcow2vt", "ramfile"]:
            with self.subTest(f"Testing unset root for backend {backend}"):
                backend_type = self._prepare_driver_from_backend(backend)
                self.run_params[f"unset_state_{backend_type}s_vm1"] = "root"

                # assert root state is detected and removed
                with self.driver.mock_show([], backend_type, True) as driver:
                    ss.unset_states(self.run_params, self.env)
                    self.mock_vms["vm1"].destroy.assert_called_once_with(gracefully=False)

    def test_qcow2_dash(self):
        """Test the special character support for the QCOW2 backends."""
        self.run_params["image_name"] = "vm1/image"

        for do in ["check", "get", "set", "unset"]:
            for state_type in ["images", "vms"]:
                with self.subTest(f"Testing QCOW2 dash processing for {do} operation on {state_type}"):
                    backend = "qcow2" if state_type == "images" else "qcow2vt"
                    backend_type = self._prepare_driver_from_backend(backend)
                    self.run_params[f"{do}_state_{state_type}"] = "launch-ready_123"

                    # check root state name format
                    with self.driver.mock_show(["launch-ready_123"], backend_type) as driver:
                        ss.__dict__[f"{do}_states"](self.run_params, self.env)
                    del self.run_params[f"{do}_state_{state_type}"]

                    # check internal state name format
                    if do == "check":
                        continue
                    self.run_params[f"{do}_state"] = "launch-ready_123"
                    run_params = self.run_params.object_params("vm1")
                    with self.driver.mock_show(["launch-ready_123"], backend_type) as driver:
                        ss.BACKENDS["qcow2"]().__getattribute__(do)(run_params, self.env)
                        ss.BACKENDS["qcow2vt"]().__getattribute__(do)(run_params, self.env)
                    del self.run_params[f"{do}_state"]

    @mock.patch('avocado_i2n.states.qcow2.os.path.isfile')
    def test_qcow2_convert(self, mock_isfile):
        """Test auxiliary qcow2 module conversion functionality."""
        self.run_params["raw_image"] = "ext_image"
        # set a generic one not restricted to vm1
        self.run_params["image_name"] = "vm1/image"
        self.run_params = self.run_params.object_params("vm1")
        backend = "qcow2"
        backend_type = self._prepare_driver_from_backend(backend)

        mock_isfile.return_value = True
        with self.driver.mock_show([], backend_type, False) as driver:
            qcow2.convert_image(self.run_params)
            driver.return_value.convert.assert_called()
            # TODO: this is now fully external assertion beyond our mocks
            # 'qemu-img convert -c -p -O qcow2 "./ext_image" "/images/vm1/image.qcow2"'

        mock_isfile.return_value = False
        with self.driver.mock_show([], backend_type, False) as driver:
            with self.assertRaises(FileNotFoundError):
                qcow2.convert_image(self.run_params)
            driver.return_value.assert_not_called()

        mock_isfile.return_value = True
        with self.driver.mock_show([], backend_type, False) as driver:
            driver.CmdError = process.CmdError
            result = process.CmdResult("qemu-img convert", stderr=b'..."write" lock...', exit_status=0)
            driver.return_value.check.side_effect = process.CmdError(result=result)
            with self.assertRaises(process.CmdError):
                qcow2.convert_image(self.run_params)
            # no convert command was executed
            driver.return_value.check.assert_called_once()
            # TODO: this is now fully external assertion beyond our mocks
            # 'qemu-img check /images/vm1/image.qcow2'
            driver.return_value.assert_not_called()


@mock.patch('avocado_i2n.states.pool.os.makedirs', mock.Mock(return_value=0))
class StatesPoolTest(Test):

    def setUp(self):
        self.run_params = utils_params.Params()
        self.run_params["nets"] = "net1"
        self.run_params["vms"] = "vm1"
        self.run_params["images"] = "image1"
        self.run_params["pool_scope"] = "own shared"

        # TODO: actual stateful object treatment is not fully defined yet
        self.mock_vms = {}
        self._create_mock_vms()
        self.env = mock.MagicMock(name='env')
        self.env.get_vm = mock.MagicMock(side_effect=self._get_mock_vm)

        self.backend = None

        # disable pool locks for easier mocking
        pool.SKIP_LOCKS = True

        self.maxDiff = None

    def _set_minimal_pool_params(self):
        self.run_params["swarm_pool"] = "/images"
        self.run_params["shared_pool"] = "/data/pool"
        self.run_params["object_id"] = "vm1-abc.def"
        self.run_params["image_format"] = "qcow2"
        self.run_params["qemu_img_binary"] = "qemu-img"

        self.run_params["nets_gateway"] = ""
        self.run_params["nets_host"] = ""

    def _create_mock_sourced_backend(self, source_type="root"):
        if source_type == "root":
            self.backend = pool.RootSourcedStateBackend
            self.backend._check_root = mock.MagicMock()
            self.backend._get_root = mock.MagicMock()
            self.backend._set_root = mock.MagicMock()
            self.backend._unset_root = mock.MagicMock()
        else:
            self.backend = pool.SourcedStateBackend
            self.backend._show = mock.MagicMock()
            self.backend._check = mock.MagicMock()
            self.backend._get = mock.MagicMock()
            self.backend._set = mock.MagicMock()
            self.backend._unset = mock.MagicMock()
        self.backend.transport = mock.MagicMock()
        ss.BACKENDS = {"mock": self.backend}

    def _create_mock_transfer_backend(self):
        self.backend = pool.QCOW2ImageTransfer
        self.deps = [""]

        ops_patch = mock.patch.object(pool.QCOW2ImageTransfer, "ops", mock.MagicMock())
        ops_patch.start()
        self.addCleanup(ops_patch.stop)

        deps_patch = mock.patch.object(self.backend, "get_dependency",
                                       lambda state, _: self.deps[self.deps.index(state)+1])
        deps_patch.start()
        self.addCleanup(deps_patch.stop)

    def _get_mock_vm(self, vm_name):
        return self.mock_vms[vm_name]

    def _create_mock_vms(self):
        for vm_name in self.run_params.objects("vms"):
            self.mock_vms[vm_name] = mock.MagicMock(name=vm_name)
            self.mock_vms[vm_name].name = vm_name
            self.mock_vms[vm_name].params = self.run_params.object_params(vm_name)

    @mock.patch('avocado_i2n.states.pool.SKIP_LOCKS', False)
    @mock.patch('avocado_i2n.states.pool.fcntl')
    def test_pool_locks(self, mock_fcntl):
        """Test auxiliary pool module locks functionality."""
        self._create_mock_vms()

        image_locked = False
        with pool.image_lock("./image.qcow2", timeout=1) as lock:
            mock_fcntl.lockf.assert_called_once()
            image_locked = True
            mock_fcntl.reset_mock()

            # TODO: from a different process if we decide to from unit tests to
            # functional tests that add more elaborate setup like this
            #with pool.image_lock("./image.qcow2", timeout=1) as lock:
            #    mock_fcntl.lockf.assert_called_once()
            #    mock_fcntl.reset_mock()
            #mock_fcntl.lockf.assert_called_once()
            #mock_fcntl.reset_mock()

        self.assertTrue(image_locked)
        mock_fcntl.lockf.assert_called_once()

    @mock.patch("avocado_i2n.states.pool.os.path.exists",
                mock.MagicMock(return_value=False))
    def test_check_root(self):
        """Test that root checking prioritizes local root then pool root."""
        self.run_params["object_type"] = "images"
        self._create_mock_sourced_backend()

        # consider pool root with priority
        self.backend._check_root.reset_mock()
        self.backend.transport.check_root.reset_mock()
        self.backend._check_root.return_value = False
        self.backend.transport.check_root.return_value = True
        exists = self.backend.check_root(self.run_params, self.env)
        self.backend._check_root.assert_called_once()
        self.backend.transport.check_root.assert_called_once()
        self.assertTrue(exists)

        # consider local root as well
        self.backend._check_root.reset_mock()
        self.backend.transport.check_root.reset_mock()
        self.backend._check_root.return_value = True
        self.backend.transport.check_root.return_value = False
        exists = self.backend.check_root(self.run_params, self.env)
        self.backend._check_root.assert_called_once()
        self.backend.transport.check_root.assert_called_once()
        self.assertTrue(exists)

        # the root state does not exist if both counterparts do not exist
        self.backend._check_root.reset_mock()
        self.backend.transport.check_root.reset_mock()
        self.backend._check_root.return_value = False
        self.backend.transport.check_root.return_value = False
        exists = self.backend.check_root(self.run_params, self.env)
        self.backend._check_root.assert_called_once()
        self.backend.transport.check_root.assert_called_once()
        self.assertFalse(exists)

    def test_check_root_use(self):
        """Test that root checking uses only local root with disabled pool."""
        self.run_params["pool_scope"] = "own"
        self._create_mock_sourced_backend()

        self.backend._check_root.return_value = False
        exists = self.backend.check_root(self.run_params, self.env)
        self.backend._check_root.assert_called_once()
        self.backend.transport.check_root.assert_not_called()
        self.assertFalse(exists)

    def test_get_root(self):
        """Test that root getting with the pool backend works."""
        self._set_minimal_pool_params()
        self.run_params["vms_base_dir"] = "/images"
        self.run_params["image_name"] = "image1"
        self._create_mock_sourced_backend()

        # consider local root with priority if valid
        self.backend._get_root.reset_mock()
        self.backend.transport.reset_mock()
        self.backend._check_root.return_value = True
        self.backend.transport.check_root.return_value = True
        self.backend.transport.ops.compare.return_value = True
        self.backend.get_root(self.run_params, self.env)
        self.backend._get_root.assert_called_once()
        self.backend.transport.get_root.assert_not_called()
        self.backend.transport.ops.compare.assert_called_once_with('/images/vm1/image1.qcow2',
                                                                   ':/data/pool/vm1/image1.qcow2',
                                                                   mock.ANY)

        # use pool root if enabled and no local root
        self.backend._get_root.reset_mock()
        self.backend.transport.reset_mock()
        self.backend._check_root.return_value = False
        self.backend.transport.check_root.return_value = True
        self.backend.get_root(self.run_params, self.env)
        self.backend._get_root.assert_called_once()
        self.backend.transport.get_root.assert_called_once()
        self.backend.transport.ops.compare.assert_not_called()

        # use pool root if local root is not valid
        self.backend._get_root.reset_mock()
        self.backend.transport.reset_mock()
        self.backend._check_root.return_value = True
        self.backend.transport.check_root.return_value = True
        self.backend.transport.ops.compare.return_value = False
        self.backend.get_root(self.run_params, self.env)
        self.backend._get_root.assert_called_once()
        self.backend.transport.get_root.assert_called_once()
        self.backend.transport.ops.compare.assert_called_once_with('/images/vm1/image1.qcow2',
                                                                   ':/data/pool/vm1/image1.qcow2',
                                                                   mock.ANY)

    def test_get_root_use(self):
        """Test that root getting uses only local root with disabled pool."""
        self.run_params["pool_scope"] = "own"
        self._create_mock_sourced_backend()

        self.backend.get_root(self.run_params, self.env)
        self.backend._get_root.assert_called_once()
        self.backend.transport.get_root.assert_not_called()

    def test_get_root_update(self):
        """Test that root getting can be forced to pool only via the update switch."""
        self.run_params["pool_scope"] = "shared"
        self._create_mock_sourced_backend()

        self.backend.get_root(self.run_params, self.env)
        self.backend._get_root.assert_not_called()
        self.backend.transport.get_root.assert_called_once()

    def test_set_root(self):
        """Test that root setting with the pool backend works."""
        self._create_mock_sourced_backend()

        # not updating the state pool means setting the local root
        self.run_params["pool_scope"] = "own"
        self.backend._check_root.return_value = True
        self.backend._set_root.reset_mock()
        self.backend.transport.set_root.reset_mock()
        self.backend.set_root(self.run_params, self.env)
        self.backend._set_root.assert_called_once()
        self.backend.transport.set_root.assert_not_called()

        # updating the state pool means not setting the local root
        self.run_params["pool_scope"] = "shared"
        self.backend._check_root.return_value = True
        self.backend._set_root.reset_mock()
        self.backend.transport.set_root.reset_mock()
        self.backend.set_root(self.run_params, self.env)
        self.backend._set_root.assert_not_called()
        self.backend.transport.set_root.assert_called_once()

    def test_set_root_update(self):
        """Test that updating the state pool without local root fails early."""
        self.run_params["pool_scope"] = "shared"
        self._create_mock_sourced_backend()

        self.backend._check_root.return_value = False
        with self.assertRaises(RuntimeError):
            self.backend.set_root(self.run_params, self.env)
        self.backend.transport.assert_not_called()

    def test_unset_root(self):
        """Test that root unsetting with the pool backend works."""
        self._create_mock_sourced_backend()

        # not updating the state pool means unsetting the local root
        self.run_params["pool_scope"] = "own"
        self.backend._check_root.return_value = True
        self.backend._unset_root.reset_mock()
        self.backend.transport.unset_root.reset_mock()
        self.backend.unset_root(self.run_params, self.env)
        self.backend._unset_root.assert_called_once()
        self.backend.transport.unset_root.assert_not_called()

        # updating the state pool means not unsetting the local root
        self.run_params["pool_scope"] = "shared"
        self.backend._check_root.return_value = True
        self.backend._unset_root.reset_mock()
        self.backend.transport.unset_root.reset_mock()
        self.backend.unset_root(self.run_params, self.env)
        self.backend._unset_root.assert_not_called()
        self.backend.transport.unset_root.assert_called_once()

    def test_show_all(self):
        """Test that state listing finds both cache and pool states."""
        self._set_minimal_pool_params()
        self.run_params["show_location"] = f":/path/1 :/path/2 :{self.run_params['swarm_pool']} :{self.run_params['shared_pool']}"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["a", "b", "c"]
        self.backend.transport.show.side_effect = lambda params, _: ["c", "d"] if "1" in params["show_location"] else ["d", "e"]
        states = self.backend.show(self.run_params, self.env)
        self.backend._show.assert_called_once()

        detected_calls = self.backend.transport.show.call_args_list
        self.assertEqual(len(detected_calls), 3)
        path1_params = detected_calls[0].args[0]
        path2_params = detected_calls[1].args[0]
        shared_params = detected_calls[2].args[0]
        #self.assertEqual(path1_params[f"show_location"], ":/path/1")
        self.assertEqual(path2_params[f"show_location"], ":/path/2")
        # no duplicate call to own scope and extra call to shared scope were made
        self.assertTrue(shared_params["show_location"], self.run_params['shared_pool'])

        self.assertSetEqual(set(states), set(["a", "b", "c", "d"]))

    def test_show_no_pool(self):
        """Test that only cache states are considered if pool is disabled."""
        self._set_minimal_pool_params()
        self.run_params["pool_scope"] = "own"
        self.run_params["show_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["a", "b", "c"]
        self.backend.transport.show.return_value = ["c", "d", "e"]
        states = self.backend.show(self.run_params, self.env)
        self.backend._show.assert_called_once()
        self.backend.transport.show.assert_not_called()
        self.assertSetEqual(set(states), set(["a", "b", "c"]))

    def test_show_only_pool(self):
        """Test that only pool states are considered if pool is enforced."""
        self._set_minimal_pool_params()
        self.run_params["pool_scope"] = "shared"
        self.run_params["show_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["a", "b", "c"]
        self.backend.transport.show.return_value = ["c", "d", "e"]
        states = self.backend.show(self.run_params, self.env)
        self.backend._show.assert_not_called()
        self.backend.transport.show.assert_called_once()
        self.assertSetEqual(set(states), set(["c", "d", "e"]))

    def test_show_cache_leftover(self):
        """Test that cache states are shown if no pool sources."""
        self._set_minimal_pool_params()
        self.run_params["check_state"] = "launch"
        self.run_params["show_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["launch", "launch2"]
        self.backend.transport.show.return_value = ["launch", "launch2"]
        exists = self.run_params["check_state"] in self.backend.show(self.run_params, self.env)
        self.backend._show.assert_called_once()
        self.backend.transport.show.assert_called_once()
        self.assertTrue(exists)

    def test_show_pool_none(self):
        """Test that no states are shown if both counterparts do not exist."""
        self._set_minimal_pool_params()
        self.run_params["check_state"] = "launch"
        self.run_params["show_location"] = ":/path/1 :/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = []
        self.backend.transport.show.return_value = []
        exists = self.run_params["check_state"] in self.backend.show(self.run_params, self.env)
        self.backend._show.assert_called_once()
        self.backend.transport.show.assert_called_once()
        self.assertFalse(exists)

    def test_get_best_source_scope(self):
        """Test that state getting chooses the best available mirror if provided with multiple choices."""
        self._set_minimal_pool_params()
        self.run_params["get_state"] = "launch"
        self.run_params["get_location"] = "alpha.c1:/path/1 beta.c1:/path2 beta.c2:/path/2 beta.c2:/own/images gamma:/path/3/4"

        self.run_params["nets_gateway_alpha.c1"] = "alpha"
        self.run_params["nets_host_alpha.c1"] = "c1"
        self.run_params["nets_gateway_beta.c1"] = "beta"
        self.run_params["nets_host_beta.c1"] = "c1"
        self.run_params["nets_gateway_beta.c2"] = "beta"
        self.run_params["nets_host_beta.c2"] = "c2"
        self.run_params["nets_gateway_gamma"] = ""
        self.run_params["nets_host_gamma"] = "gamma"
        self.run_params["nets_gateway"] = "beta"
        self.run_params["nets_host"] = "c2"
        self.run_params["swarm_pool"] = "/own/images"

        self._create_mock_sourced_backend(source_type="state")

        self.backend._check.return_value = False
        self.backend.transport.check.return_value = True

        sources = self.backend.get_sources("get", self.run_params)
        self.assertListEqual(sources, ["beta.c2:/own/images", "beta.c2:/path/2", "beta.c1:/path2",
                                       "alpha.c1:/path/1", "gamma:/path/3/4"])
        scopes = ["own", "shared", "swarm", "cluster", "cluster"]
        for i in range(len(sources)):
            host, path = sources[i].split(":")
            source_params = self.run_params.object_params(host)
            self.assertEqual(self.backend.get_source_scope(path, source_params, self.run_params), scopes[i])

    def test_get_valid_cache(self):
        """Test that state getting considers cache state with priority if hash matches with one transport location."""
        self._set_minimal_pool_params()
        self.run_params["get_state"] = "launch"
        self.run_params["get_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["launch"]
        self.backend.transport.show.return_value = ["launch"]
        self.backend.transport.compare_chain.return_value = True

        self.backend.get(self.run_params, self.env)
        self.backend._get.assert_called_once()
        self.backend.transport.get.assert_not_called()
        self.backend.transport.compare_chain.assert_called_once_with("launch", "/images", ":/path/1", mock.ANY)

    def test_get_no_cache(self):
        """Test that state getting uses pool state if enabled and no local root."""
        self._set_minimal_pool_params()
        self.run_params["get_state"] = "launch"
        self.run_params["get_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = []
        self.backend.transport.show.return_value = ["launch"]

        self.backend.get(self.run_params, self.env)

        self.backend._get.assert_called_once()
        self.backend.transport.get.assert_called_once()
        self.backend.transport.compare_chain.assert_not_called()

    def test_get_invalid_cache(self):
        """Test that state getting uses pool state if local state is not valid."""
        self._set_minimal_pool_params()
        self.run_params["get_state"] = "launch"
        self.run_params["get_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["launch"]
        self.backend.transport.show.return_value = ["launch"]
        self.backend.transport.compare_chain.return_value = False

        self.backend.get(self.run_params, self.env)

        self.backend._get.assert_called_once()
        self.backend.transport.get.assert_called_once()
        self.backend.transport.compare_chain.assert_called_once_with("launch", "/images", ":/path/1", mock.ANY)

    def test_get_no_pool(self):
        """Test that state getting uses only local root with disabled pool."""
        self._set_minimal_pool_params()
        self.run_params["pool_scope"] = "own"
        self.run_params["get_state"] = "launch"
        self.run_params["get_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend.get(self.run_params, self.env)
        self.backend._get.assert_called_once()
        self.backend.transport.get.assert_not_called()

    def test_get_only_pool(self):
        """Test that state getting can be forced to pool only via the update switch."""
        self._set_minimal_pool_params()
        self.run_params["pool_scope"] = "shared"
        self.run_params["get_state"] = "launch"
        self.run_params["get_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = []
        self.backend.transport.show.return_value = ["launch"]

        self.backend.get(self.run_params, self.env)
        self.backend._get.assert_not_called()
        self.backend.transport.get.assert_called_once()

    def test_get_own(self):
        """Test that state getting uses only local root with disabled pool."""
        self._set_minimal_pool_params()
        self.run_params["get_state"] = "launch"
        self.run_params["get_location"] = f":/path/1 :{self.run_params['swarm_pool']}"
        self._create_mock_sourced_backend(source_type="state")

        self.backend.get(self.run_params, self.env)
        self.backend._get.assert_called_once()
        self.backend.transport.get.assert_not_called()

    def test_set_all(self):
        """Test that state setting works with both cache and multiple transports."""
        self._set_minimal_pool_params()
        self.run_params["set_state"] = "launch"
        self.run_params["set_location"] = f":/path/1 :/path/2 :{self.run_params['swarm_pool']} :{self.run_params['shared_pool']}"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["launch"]
        self.backend.set(self.run_params, self.env)
        self.backend._set.assert_called_once()

        detected_calls = self.backend.transport.set.call_args_list
        self.assertEqual(len(detected_calls), 3)
        path1_params = detected_calls[0].args[0]
        path2_params = detected_calls[1].args[0]
        shared_params = detected_calls[2].args[0]
        self.assertEqual(path1_params[f"set_location"], ":/path/1")
        self.assertEqual(path2_params[f"set_location"], ":/path/2")
        # no duplicate call to own scope and extra call to shared scope were made
        self.assertTrue(shared_params["set_location"], self.run_params['shared_pool'])

    def test_set_no_pool(self):
        """Test that not updating the state pool sets just the cache state."""
        self._set_minimal_pool_params()
        self.run_params["pool_scope"] = "own"
        self.run_params["set_state"] = "launch"
        self.run_params["set_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["launch"]
        self.backend.set(self.run_params, self.env)
        self.backend._set.assert_called_once()
        self.backend.transport.set.assert_not_called()

    def test_set_only_pool(self):
        """Test that updating the state pool does not set the cache state."""
        self._set_minimal_pool_params()
        self.run_params["pool_scope"] = "shared"
        self.run_params["set_state"] = "launch"
        self.run_params["set_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["launch"]
        self.backend.set(self.run_params, self.env)
        self.backend._set.assert_not_called()
        self.backend.transport.set.assert_called_once()

    def test_set_only_pool_no_cache(self):
        """Test that updating the state pool without cache state fails early."""
        self._set_minimal_pool_params()
        self.run_params["pool_scope"] = "shared"
        self.run_params["set_state"] = "launch"
        self.run_params["set_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = []
        with self.assertRaises(RuntimeError):
            self.backend.set(self.run_params, self.env)
        self.backend.transport.assert_not_called()

    def test_unset_all(self):
        """Test that state unsetting works with both cache and multiple transports."""
        self._set_minimal_pool_params()
        self.run_params["unset_state"] = "launch"
        self.run_params["unset_location"] = f":/path/1 :/path/2 :{self.run_params['swarm_pool']} :{self.run_params['shared_pool']}"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["launch"]
        self.backend.unset(self.run_params, self.env)
        self.backend._unset.assert_called_once()

        detected_calls = self.backend.transport.unset.call_args_list
        self.assertEqual(len(detected_calls), 3)
        path1_params = detected_calls[0].args[0]
        path2_params = detected_calls[1].args[0]
        shared_params = detected_calls[2].args[0]
        self.assertEqual(path1_params[f"unset_location"], ":/path/1")
        self.assertEqual(path2_params[f"unset_location"], ":/path/2")
        # no duplicate call to own scope and extra call to shared scope were made
        self.assertTrue(shared_params["unset_location"], self.run_params['shared_pool'])

    def test_unset_only_pool(self):
        """Test that not updating the state pool unsets just the cache state."""
        self._set_minimal_pool_params()
        self.run_params["pool_scope"] = "own"
        self.run_params["unset_state"] = "launch"
        self.run_params["unset_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["launch"]
        self.backend.unset(self.run_params, self.env)
        self.backend._unset.assert_called_once()
        self.backend.transport.unset.assert_not_called()

    def test_unset_no_pool(self):
        """Test that updating the state pool does not unset the cache state."""
        self._set_minimal_pool_params()
        self.run_params["pool_scope"] = "shared"
        self.run_params["unset_state"] = "launch"
        self.run_params["unset_location"] = ":/path/1"
        self._create_mock_sourced_backend(source_type="state")

        self.backend._show.return_value = ["launch"]
        self.backend.unset(self.run_params, self.env)
        self.backend._unset.assert_not_called()
        self.backend.transport.unset.assert_called_once()

    def test_list_bundle(self):
        """Test that a state bundle (e.g. image with internal states) will be listed."""
        self._set_minimal_pool_params()
        self.run_params["vms_base_dir"] = "/images"
        self.run_params["image_name"] = "image1"

        self._create_mock_transfer_backend()

        self.backend.ops.list_paths.return_value = ["image1.qcow2"]
        exists = self.backend.check_root(self.run_params, self.env)
        self.backend.ops.list_paths.assert_called_with(":/data/pool/vm1", mock.ANY)
        self.assertTrue(exists)

    def test_list_chain_image(self):
        """Test that a state and its complete backing chain will be listed."""
        self._set_minimal_pool_params()
        self.run_params["check_state"] = "launch"
        self.run_params["show_location"] = "container.host:/dir/subdir"
        self.run_params["object_type"] = "nets/vms/images"

        self._create_mock_transfer_backend()
        self.deps = ["launch", "prelaunch", ""]

        self.backend.ops.list_paths.return_value = ["launch.qcow2", "prelaunch.qcow2"]
        exists = self.run_params["check_state"] in self.backend.show(self.run_params, self.env)
        expected_checks = [mock.call("container.host:/dir/subdir/vm1-abc.def/image1", mock.ANY)]
        self.assertListEqual(self.backend.ops.list_paths.call_args_list, expected_checks)
        self.assertTrue(exists)

    def test_list_chain_vm(self):
        """Test that a state and its complete backing chain will be listed."""
        self._set_minimal_pool_params()
        self.run_params["check_state"] = "launch"
        self.run_params["show_location"] = "container.host:/dir/subdir"
        self.run_params["object_type"] = "nets/vms"

        self._create_mock_transfer_backend()
        self.deps = ["launch", "prelaunch", ""]

        self.backend.ops.list_paths.return_value = ["launch.state", "prelaunch.state"]
        exists = self.run_params["check_state"] in self.backend.show(self.run_params, self.env)
        expected_checks = [mock.call("container.host:/dir/subdir/vm1-abc.def", mock.ANY)]
        self.assertListEqual(self.backend.ops.list_paths.call_args_list, expected_checks)
        self.assertTrue(exists)

    def test_compare_chain_valid(self):
        """Test that a local and remote state and their complete backing chains are validated."""
        self._set_minimal_pool_params()
        self.run_params["image_name"] = "image1"
        self.run_params["object_type"] = "nets/vms/images"

        self._create_mock_transfer_backend()
        self.deps = ["launch", "prelaunch", ""]
        location = "container.host:/dir/subdir"

        # the states chains are identical
        self.backend.ops.reset_mock()
        self.backend.ops.compare.return_value = True
        valid = self.backend.compare_chain("launch", "/images", location, self.run_params)
        expected_checks = [mock.call("/images/vm1-abc.def/image1/launch.qcow2",
                                     os.path.join(location, "vm1-abc.def/image1/launch.qcow2"),
                                     mock.ANY),
                           mock.call("/images/vm1-abc.def/image1/prelaunch.qcow2",
                                     os.path.join(location, "vm1-abc.def/image1/prelaunch.qcow2"),
                                     mock.ANY)]
        self.assertListEqual(self.backend.ops.compare.call_args_list, expected_checks)
        self.assertTrue(valid)

        # the states chains are not identical
        self.deps = ["launch", "invalid", "prelaunch", ""]
        self.backend.ops.reset_mock()
        self.backend.ops.compare.side_effect = lambda x, _, __: True if "invalid" in x else False
        valid = self.backend.compare_chain("launch", "/images", location, self.run_params)
        expected_checks = [mock.call("/images/vm1-abc.def/image1/launch.qcow2",
                                     os.path.join(location, "vm1-abc.def/image1/launch.qcow2"),
                                     mock.ANY)]
        self.assertListEqual(self.backend.ops.compare.call_args_list, expected_checks)
        self.assertFalse(valid)

    def test_download_bundle(self):
        """Test that a state bundle (e.g. image with internal states) will be downloaded."""
        self._set_minimal_pool_params()
        self.run_params["vms_base_dir"] = "/images"
        self.run_params["image_name"] = "image1"

        self._create_mock_transfer_backend()

        self.backend.get_root(self.run_params, self.env)
        self.backend.ops.download.assert_called_with("/images/vm1/image1.qcow2",
                                                     ":/data/pool/vm1/image1.qcow2",
                                                     mock.ANY)

    def test_download_chain(self):
        """Test that a state and its complete backing chain will be downloaded."""
        self._set_minimal_pool_params()
        self.run_params["get_state"] = "launch"
        self.run_params["get_location"] = "container.host:/dir/subdir"
        self.run_params["object_type"] = "nets/vms/images"

        self._create_mock_transfer_backend()
        self.deps = ["launch", "prelaunch", ""]

        self.backend.get(self.run_params, self.env)
        expected_checks = [mock.call("/images/vm1-abc.def/image1/launch.qcow2",
                                     "container.host:/dir/subdir/vm1-abc.def/image1/launch.qcow2", mock.ANY),
                           mock.call("/images/vm1-abc.def/image1/prelaunch.qcow2",
                                     "container.host:/dir/subdir/vm1-abc.def/image1/prelaunch.qcow2", mock.ANY)]
        self.assertListEqual(self.backend.ops.download.call_args_list, expected_checks)

    def test_upload_bundle(self):
        """Test that a state bundle (e.g. image with internal states) will be uploaded."""
        self._set_minimal_pool_params()
        self.run_params["vms_base_dir"] = "/images"
        self.run_params["image_name"] = "image1"

        self._create_mock_transfer_backend()

        self.backend.set_root(self.run_params, self.env)
        self.backend.ops.upload.assert_called_with("/images/vm1/image1.qcow2",
                                                   ":/data/pool/vm1/image1.qcow2",
                                                   mock.ANY)

    def test_upload_chain(self):
        """Test that a state and its complete backing chain will be uploaded."""
        self._set_minimal_pool_params()
        self.run_params["set_state"] = "launch"
        self.run_params["set_location"] = "container.host:/dir/subdir"
        self.run_params["object_type"] = "nets/vms/images"

        self._create_mock_transfer_backend()
        self.deps = ["launch", "prelaunch", ""]

        self.backend.set(self.run_params, self.env)
        expected_checks = [mock.call("/images/vm1-abc.def/image1/launch.qcow2",
                                     "container.host:/dir/subdir/vm1-abc.def/image1/launch.qcow2", mock.ANY),
                           mock.call("/images/vm1-abc.def/image1/prelaunch.qcow2",
                                     "container.host:/dir/subdir/vm1-abc.def/image1/prelaunch.qcow2", mock.ANY)]
        self.assertListEqual(self.backend.ops.upload.call_args_list, expected_checks)

    def test_delete_bundle(self):
        """Test that a state bundle (e.g. image with internal states) will be deleted."""
        self._set_minimal_pool_params()
        self.run_params["vms_base_dir"] = "/images"
        self.run_params["image_name"] = "image1"

        self._create_mock_transfer_backend()

        self.backend.unset_root(self.run_params, self.env)
        self.backend.ops.delete.assert_called_with(":/data/pool/vm1/image1.qcow2",
                                                   mock.ANY)

    def test_delete_chain(self):
        """Test that a state but not its complete backing chain will be deleted."""
        self._set_minimal_pool_params()
        self.run_params["unset_state"] = "launch"
        self.run_params["unset_location"] = "container.host:/dir/subdir"
        self.run_params["object_type"] = "nets/vms/images"

        self._create_mock_transfer_backend()
        self.deps = ["launch", "prelaunch", ""]

        self.backend.unset(self.run_params, self.env)
        expected_checks = [mock.call("container.host:/dir/subdir/vm1-abc.def/image1/launch.qcow2", mock.ANY)]
        self.assertListEqual(self.backend.ops.delete.call_args_list, expected_checks)

    def test_location_parameter_propagation(self):
        """Test that each transport call of pool enabled backend uses source specific parameters."""
        self._set_minimal_pool_params()
        self.run_params["pool_scope"] += " swarm cluster"
        self._create_mock_sourced_backend(source_type="state")

        self.run_params["nets_gateway_c1.h1"] = "h1"
        self.run_params["nets_host_c1.h1"] = "c1"
        self.run_params["nets_shell_port_c1.h1"] = "22001"
        self.run_params["nets_gateway_c2.h2"] = "h2"
        self.run_params["nets_host_c2.h2"] = "c2"
        self.run_params["nets_shell_port_c2.h2"] = "22002"

        for do in ["show", "get", "set", "unset"]:
            with self.subTest(f"Testing location parameter propagation for {do}"):
                self.run_params[f"{do}_state"] = "launch"
                self.run_params[f"{do}_location"] = "c1.h1:/path/1 c2.h2:/path/2"
                self.run_params["nets_gateway"] = "h1"
                self.run_params["nets_host"] = "c1"

                self.backend.transport.reset_mock()
                if do == "show":
                    self.backend.show(self.run_params, self.env)
                    detected_calls = self.backend.transport.show.call_args_list
                elif do == "get":
                    self.backend._show.return_value = []
                    self.backend.transport.show.return_value = ["launch"]
                    self.backend.get(self.run_params, self.env)
                    self.run_params["nets_gateway"] = "h2"
                    self.backend.get(self.run_params, self.env)
                    detected_calls = self.backend.transport.get.call_args_list
                elif do == "set":
                    self.backend.set(self.run_params, self.env)
                    detected_calls = self.backend.transport.set.call_args_list
                elif do == "unset":
                    self.backend.unset(self.run_params, self.env)
                    detected_calls = self.backend.transport.unset.call_args_list
                else:
                    raise ValueError("Invalid state manipulation under testing")
                self.assertEqual(len(detected_calls), 2)
                source1_params = detected_calls[0].args[0]
                source2_params = detected_calls[1].args[0]
                self.assertEqual(source1_params[f"{do}_location"], "c1.h1:/path/1")
                self.assertEqual(source2_params[f"{do}_location"], "c2.h2:/path/2")
                self.assertIn("nets_shell_port", source1_params)
                self.assertTrue(source1_params["nets_shell_port"], "22001")
                self.assertIn("nets_shell_port", source2_params)
                self.assertTrue(source2_params["nets_shell_port"], "22002")

    def test_location_scope_blocking(self):
        """Test that requested transport location scopes are fully blocked."""
        self._set_minimal_pool_params()
        self.run_params["pool_scope"] += " swarm"
        self._create_mock_sourced_backend(source_type="state")

        self.run_params["nets_gateway_c1.h1"] = "h1"
        self.run_params["nets_host_c1.h1"] = "c1"
        self.run_params["nets_gateway_c2.h2"] = "h2"
        self.run_params["nets_host_c2.h2"] = "c2"

        for do in ["show", "get", "set", "unset"]:
            with self.subTest(f"Testing location scope blocking for {do}"):
                self.run_params[f"{do}_state"] = "launch"
                self.run_params[f"{do}_location"] = "c1.h1:/path/1 c2.h2:/path/2"
                self.run_params["nets_gateway"] = "h2"
                self.run_params["nets_host"] = "c2"
                self.backend.transport.reset_mock()
                if do == "show":
                    self.backend.show(self.run_params, self.env)
                    detected_calls = self.backend.transport.show.call_args_list
                elif do == "get":
                    self.backend._show.return_value = []
                    self.backend.transport.show.return_value = ["launch"]
                    self.backend.get(self.run_params, self.env)
                    detected_calls = self.backend.transport.get.call_args_list
                elif do == "set":
                    self.backend.set(self.run_params, self.env)
                    detected_calls = self.backend.transport.set.call_args_list
                elif do == "unset":
                    self.backend.unset(self.run_params, self.env)
                    detected_calls = self.backend.transport.unset.call_args_list
                else:
                    raise ValueError("Invalid state manipulation under testing")
                self.assertEqual(len(detected_calls), 1)
                source_params = detected_calls[0].args[0]
                self.assertEqual(source_params[f"{do}_location"], "c2.h2:/path/2")

    def test_local_pool_override(self):
        """Test that correct cache and shared locations are overriden via configuration."""
        self._set_minimal_pool_params()

        self._create_mock_transfer_backend()
        self.deps = ["launch", "prelaunch", ""]

        for do in ["get", "set", "unset"]:
            for swarm_pool in ["/swarm", "/some/swarm2"]:
                for shared_pool in [":/shared", "container.host:/else"]:
                    with self.subTest(f"Override swarm pool with {swarm_pool} and shared pool with {shared_pool} via {do}"):

                        self.run_params[f"{do}_state"] = "launch"
                        self.run_params[f"{do}_location"] = shared_pool
                        self.run_params["object_type"] = "nets/vms/images"
                        # TODO: have to integrate this implicit overwriting into the location params
                        self.run_params["swarm_pool"] = swarm_pool
                        location = swarm_pool

                        self.backend.ops.reset_mock()
                        if do == "get":
                            self.backend.get(self.run_params, self.env)
                            expected_checks = [mock.call(f"{location}/vm1-abc.def/image1/launch.qcow2",
                                                         f"{shared_pool}/vm1-abc.def/image1/launch.qcow2",
                                                         mock.ANY),
                                               mock.call(f"{location}/vm1-abc.def/image1/prelaunch.qcow2",
                                                         f"{shared_pool}/vm1-abc.def/image1/prelaunch.qcow2",
                                                         mock.ANY)]
                            self.assertListEqual(self.backend.ops.download.call_args_list, expected_checks)
                        elif do == "set":
                            self.backend.set(self.run_params, self.env)
                            expected_checks = [mock.call(f"{location}/vm1-abc.def/image1/launch.qcow2",
                                                         f"{shared_pool}/vm1-abc.def/image1/launch.qcow2",
                                                         mock.ANY),
                                            mock.call(f"{location}/vm1-abc.def/image1/prelaunch.qcow2",
                                                      f"{shared_pool}/vm1-abc.def/image1/prelaunch.qcow2",
                                                      mock.ANY)]
                            self.assertListEqual(self.backend.ops.upload.call_args_list, expected_checks)
                        elif do == "unset":
                            self.backend.unset(self.run_params, self.env)
                            expected_checks = [mock.call(f"{shared_pool}/vm1-abc.def/image1/launch.qcow2", mock.ANY)]
                            self.assertListEqual(self.backend.ops.delete.call_args_list, expected_checks)
                        else:
                            raise ValueError("Invalid state manipulation under testing")

    def test_remote_boundary_path(self):
        """Test that the correct transport ops have been used for each state operation."""
        self._set_minimal_pool_params()

        self._create_mock_transfer_backend()
        self.deps = ["launch", ""]

        for do in ["show", "get", "set", "unset"]:
            for i, pool_source in enumerate([":/shared", ":/shared;", "container.host:/else"]):
                with self.subTest(f"Testing transport ops for {do} and shared pool {pool_source}"):
                    self.run_params[f"{do}_state"] = "launch"
                    self.run_params[f"{do}_location"] = pool_source
                    self.run_params["object_type"] = "nets/vms/images"

                    # create a spec-binding mock class instead of resetting previous mock
                    self.backend.ops = mock.Mock(spec=pool.TransferOps)

                    # assign a bound class method to the mock object with the mock class as the class object
                    # MyMockClass.my_classmethod = types.MethodType(MyClass.my_classmethod.__func__, MyMockClass)
                    # SPECIAL NOTE: to assign a bound instance method to the mock object with the mock object as self:
                    # my_mock.my_method = MyClass.my_method.__get__(my_mock)

                    if do == "show":
                        self.backend.ops.list_local.return_value = []
                        self.backend.ops.list_link.return_value = []
                        self.backend.ops.list_remote.return_value = []
                        self.backend.ops.list_paths = types.MethodType(pool.TransferOps.list_paths.__func__, self.backend.ops)
                        self.backend.show(self.run_params, self.env)
                        if i == 0:
                            self.backend.ops.list_local.assert_called_once()
                        elif i == 1:
                            self.backend.ops.list_link.assert_called_once()
                        else:
                            self.backend.ops.list_remote.assert_called_once()
                    elif do == "get":
                        self.backend.ops.download = types.MethodType(pool.TransferOps.download.__func__, self.backend.ops)
                        self.backend.get(self.run_params, self.env)
                        if i == 0:
                            self.backend.ops.download_local.assert_called_once()
                        elif i == 1:
                            self.backend.ops.download_link.assert_called_once()
                        else:
                            self.backend.ops.download_remote.assert_called_once()
                    elif do == "set":
                        self.backend.ops.upload = types.MethodType(pool.TransferOps.upload.__func__, self.backend.ops)
                        self.backend.set(self.run_params, self.env)
                        if i == 0:
                            self.backend.ops.upload_local.assert_called_once()
                        elif i == 1:
                            self.backend.ops.upload_link.assert_called_once()
                        else:
                            self.backend.ops.upload_remote.assert_called_once()
                    elif do == "unset":
                        self.backend.ops.delete = types.MethodType(pool.TransferOps.delete.__func__, self.backend.ops)
                        self.backend.unset(self.run_params, self.env)
                        if i == 0:
                            self.backend.ops.delete_local.assert_called_once()
                        elif i == 1:
                            self.backend.ops.delete_link.assert_called_once()
                        else:
                            self.backend.ops.delete_remote.assert_called_once()
                    else:
                        raise ValueError("Invalid state manipulation under testing")


class StatesSetupTest(Test):

    def setUp(self):
        self.run_params = utils_params.Params()
        self.run_params["vms"] = "vm1"

        # TODO: actual stateful object treatment is not fully defined yet
        self.mock_vms = {}
        self._create_mock_vms()
        self.env = mock.MagicMock(name='env')
        self.env.get_vm = mock.MagicMock(side_effect=self._get_mock_vm)

        # satisfy subclass checks for our mock spy methods
        def mock_class(cls):
            class meta(type):
                def __getattribute__(self, name):
                    try:
                        return getattr(m, name)
                    except AttributeError:
                        return getattr(cls, name)
            m = mock.MagicMock(spec_set=cls)
            return meta(cls.__name__, cls.__bases__, {})
        self.backend = mock_class(ss.StateBackend)
        ss.BACKENDS = {"mock": self.backend}

    def _set_up_generic_params(self, state_op, state_name, state_type, state_object):
        self.run_params["states_chain"] = state_type
        self.run_params[f"states_{state_type}"] = "mock"
        self.run_params[state_type] = state_object
        self.run_params[f"{state_op}_state_{state_type}_{state_object}"] = state_name
        self.run_params[f"{state_op}_location_{state_type}_{state_object}"] = "/loc"

    def _set_up_multiobj_params(self):
        self.run_params["nets"] = "net1"
        self.run_params["images"] = "image1"
        self.run_params["main_vm"] = "vm1"
        self.run_params["image_name_vm1"] = "image"
        self.run_params["vms_base_dir"] = "/images"
        self.run_params["images_base_dir_vm1"] = "/images/vm1"
        self.run_params["nets"] = "net1"
        self.run_params["states_chain"] = "nets vms images"
        self.run_params["states_nets"] = "mock"
        self.run_params["states_images"] = "mock"
        self.run_params["states_vms"] = "mock"
        self.run_params["check_mode"] = "rr"

    def _get_mock_vm(self, vm_name):
        return self.mock_vms[vm_name]

    def _create_mock_vms(self):
        for vm_name in self.run_params.objects("vms"):
            self.mock_vms[vm_name] = mock.MagicMock(name=vm_name)
            self.mock_vms[vm_name].name = vm_name
            self.mock_vms[vm_name].params = self.run_params.object_params(vm_name)

    def test_check_root(self):
        """Test that state checking with a state backend can get roots."""
        self._set_up_generic_params("check", "state", "objects", "object1")

        # assert root state is not detected then created to check the actual state
        self.backend.check_root.return_value = True
        self.backend.show.return_value = []
        exists = ss.check_states(self.run_params, self.env)
        # assert root state is checked as a prerequisite
        self.backend.check_root.assert_called_once()
        # assert root state is always made available (provision for state checks)
        self.backend.get_root.assert_called_once()

        # assert actual state is still checked and not available
        self.backend.show.assert_called_once()
        self.assertFalse(exists)

    def test_check_forced_root(self):
        """Test that state checking with a state backend can set roots."""
        self._set_up_generic_params("check", "state", "objects", "object1")
        # TODO: should we check other policies or keep root-related behavior at all?
        self.run_params["check_mode"] = "ff"

        # assert root state is not detected then created to check the actual state
        self.backend.check_root.return_value = False
        self.backend.show.return_value = []
        exists = ss.check_states(self.run_params, self.env)
        # assert root state is checked as a prerequisite
        self.backend.check_root.assert_called_once()
        # assert root state is provided from the check
        self.backend.set_root.assert_called_once()

        # assert actual state is still checked and not available
        self.backend.show.assert_called_once()
        self.assertFalse(exists)

    @mock.patch("avocado_i2n.states.setup.check_states")
    def test_get(self, mock_show):
        """Test that state getting works with default policies."""
        self._set_up_generic_params("get", "state", "objects", "object1")

        # assert state retrieval is performed if state is available
        mock_show.reset()
        mock_show.return_value = True
        self.backend.reset_mock()
        ss.get_states(self.run_params, self.env)
        mock_show.assert_called_once()
        call_params = [call.args[0] for call in mock_show.call_args_list]
        self.assertEqual(len(call_params), 1)
        self.assertEqual(call_params[0]["check_state"], "state")
        self.assertEqual(call_params[0]["show_location"], "/loc")
        self.assertEqual(call_params[0]["objects"], "object1")
        self.assertEqual(call_params[0]["object_name"], "object1")
        self.assertEqual(call_params[0]["object_type"], "objects")
        self.backend.get.assert_called_once()

        # assert state retrieval is aborted if state is not available
        mock_show.reset()
        mock_show.return_value = False
        self.backend.reset_mock()
        with self.assertRaises(exceptions.TestAbortError):
            ss.get_states(self.run_params, self.env)
        self.backend.get.assert_not_called()

    def test_get_aa(self):
        """Test that state getting works with abort policies."""
        self._set_up_generic_params("get", "state", "objects", "object1")
        self.run_params["get_mode"] = "aa"

        # assert state retrieval is aborted if state is available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            with self.assertRaises(exceptions.TestAbortError):
                ss.get_states(self.run_params, self.env)
            self.backend.get.assert_not_called()

        # assert state retrieval is aborted if state is not available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            with self.assertRaises(exceptions.TestAbortError):
                ss.get_states(self.run_params, self.env)
            self.backend.get.assert_not_called()

    def test_get_rx(self):
        """Test that state getting works with reuse policy."""
        self._set_up_generic_params("get", "state", "objects", "object1")
        self.run_params["get_mode"] = "rx"

        # assert state retrieval is reused if available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            ss.get_states(self.run_params, self.env)
            self.backend.get.assert_called_once()

    def test_get_ii(self):
        """Test that state getting works with ignore policies."""
        self._set_up_generic_params("get", "state", "objects", "object1")
        self.run_params["get_mode"] = "ii"

        # assert state retrieval is ignored if state is available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            ss.get_states(self.run_params, self.env)
            self.backend.get.assert_not_called()

        # assert state retrieval is ignored if state is not available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            ss.get_states(self.run_params, self.env)
            self.backend.get.assert_not_called()

    def test_get_xx(self):
        """Test that state getting detects invalid policies."""
        self._set_up_generic_params("get", "state", "objects", "object1")
        self.run_params["get_mode"] = "xx"

        # assert invalid policy x if state is available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            with self.assertRaises(exceptions.TestError):
                ss.get_states(self.run_params, self.env)
            self.backend.get.assert_not_called()

        # assert invalid policy x if state is not available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            with self.assertRaises(exceptions.TestError):
                ss.get_states(self.run_params, self.env)
            self.backend.get.assert_not_called()

    @mock.patch("avocado_i2n.states.setup.check_states")
    def test_set(self, mock_show):
        """Test that state setting works with default policies."""
        self._set_up_generic_params("set", "state", "objects", "object1")

        # assert state saving is forced if state is available
        mock_show.reset()
        mock_show.return_value = True
        self.backend.reset_mock()
        ss.set_states(self.run_params, self.env)
        mock_show.assert_called_once()
        call_params = [call.args[0] for call in mock_show.call_args_list]
        self.assertEqual(len(call_params), 1)
        self.assertEqual(call_params[0]["check_state"], "state")
        self.assertEqual(call_params[0]["show_location"], "/loc")
        self.assertEqual(call_params[0]["objects"], "object1")
        self.assertEqual(call_params[0]["object_name"], "object1")
        self.assertEqual(call_params[0]["object_type"], "objects")
        self.backend.unset.assert_called_once()
        self.backend.set.assert_called_once()

        # assert state saving is forced if state is not available
        mock_show.reset()
        mock_show.return_value = False
        self.backend.reset_mock()
        ss.set_states(self.run_params, self.env)
        self.backend.unset.assert_not_called()
        self.backend.set.assert_called_once()

        # assert state saving cannot be forced if state root is not available
        mock_show.reset()
        mock_show.return_value = False
        self.backend.reset_mock()
        self.backend.check_root.return_value = False
        with self.assertRaises(exceptions.TestError):
            ss.set_states(self.run_params, self.env)
        self.backend.set.assert_not_called()

    def test_set_aa(self):
        """Test that state setting works with abort policies."""
        self._set_up_generic_params("set", "state", "objects", "object1")
        self.run_params["set_mode"] = "aa"

        # assert state saving is aborted if state is available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            with self.assertRaises(exceptions.TestAbortError):
                ss.set_states(self.run_params, self.env)
            self.backend.set.assert_not_called()

        # assert state saving is aborted if state is not available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            with self.assertRaises(exceptions.TestAbortError):
                ss.set_states(self.run_params, self.env)
            self.backend.set.assert_not_called()

    def test_set_rx(self):
        """Test that state setting works with reuse policy."""
        self._set_up_generic_params("set", "state", "objects", "object1")
        self.run_params["set_mode"] = "rx"

        # assert state saving is skipped if reusable state is available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            ss.set_states(self.run_params, self.env)
            self.backend.set.assert_not_called()

    def test_set_ff(self):
        """Test that state setting works with force policies."""
        self._set_up_generic_params("set", "state", "objects", "object1")
        self.run_params["set_mode"] = "ff"

        # assert state saving is forced if state is available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            ss.set_states(self.run_params, self.env)
            self.backend.unset.assert_called_once()
            self.backend.set.assert_called_once()

        # assert state saving is forced if state is not available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            ss.set_states(self.run_params, self.env)
            self.backend.unset.assert_not_called()
            self.backend.set.assert_called_once()

        # assert state saving cannot be forced if state root is not available
        self.backend.reset_mock()
        self.backend.check_root.return_value = False
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            with self.assertRaises(exceptions.TestError):
                ss.set_states(self.run_params, self.env)
            self.backend.set.assert_not_called()

    def test_set_xx(self):
        """Test that state setting detects invalid policies."""
        self._set_up_generic_params("set", "state", "objects", "object1")
        self.run_params["set_mode"] = "xx"

        # assert invalid policy x if state is available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            with self.assertRaises(exceptions.TestError):
                ss.set_states(self.run_params, self.env)
            self.backend.set.assert_not_called()

        # assert invalid policy x if state is not available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            with self.assertRaises(exceptions.TestError):
                ss.set_states(self.run_params, self.env)
            self.backend.set.assert_not_called()

    @mock.patch("avocado_i2n.states.setup.check_states")
    def test_unset(self, mock_show):
        """Test that state unsetting works with default policies."""
        self._set_up_generic_params("unset", "state", "objects", "object1")

        # assert state removal is forced if state is available
        mock_show.reset()
        mock_show.return_value = True
        self.backend.reset_mock()
        ss.unset_states(self.run_params, self.env)
        mock_show.assert_called_once()
        call_params = [call.args[0] for call in mock_show.call_args_list]
        self.assertEqual(len(call_params), 1)
        self.assertEqual(call_params[0]["check_state"], "state")
        self.assertEqual(call_params[0]["show_location"], "/loc")
        self.assertEqual(call_params[0]["objects"], "object1")
        self.assertEqual(call_params[0]["object_name"], "object1")
        self.assertEqual(call_params[0]["object_type"], "objects")
        self.backend.unset.assert_called_once()

        # assert state removal is ignored if state is not available
        mock_show.reset()
        mock_show.return_value = False
        self.backend.reset_mock()
        ss.unset_states(self.run_params, self.env)
        self.backend.unset.assert_not_called()

    def test_unset_ra(self):
        """Test that state unsetting works with reuse and abort policy."""
        self._set_up_generic_params("unset", "state", "objects", "object1")
        self.run_params["unset_mode"] = "ra"

        # assert state removal is skipped if reusable state is available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            ss.unset_states(self.run_params, self.env)
            self.backend.unset.assert_not_called()

        # assert state removal is aborted if state is not available
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            with self.assertRaises(exceptions.TestAbortError):
                ss.unset_states(self.run_params, self.env)
            self.backend.unset.assert_not_called()

    def test_unset_fi(self):
        """Test that state unsetting works with force and ignore policy."""
        self._set_up_generic_params("unset", "state", "objects", "object1")
        self.run_params["unset_mode"] = "fi"

        # assert state removal is forced if state is available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            ss.unset_states(self.run_params, self.env)
            self.backend.unset.assert_called_once()

        # assert state removal is ignored if state is not available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            ss.unset_states(self.run_params, self.env)
            self.backend.unset.assert_not_called()

    def test_unset_xx(self):
        """Test that state unsetting detects invalid policies."""
        self._set_up_generic_params("unset", "state", "objects", "object1")
        self.run_params["unset_mode"] = "xx"

        # assert invalid policy x if state is available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            with self.assertRaises(exceptions.TestError):
                ss.unset_states(self.run_params, self.env)
            self.backend.unset.assert_not_called()

        # assert invalid policy x if state is not available
        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            with self.assertRaises(exceptions.TestError):
                ss.unset_states(self.run_params, self.env)
            self.backend.unset.assert_not_called()

    def test_push(self):
        """Test that pushing with a state backend works."""
        self._set_up_generic_params("push", "state", "objects", "object1")
        self.run_params["push_mode"] = "ff"

        self.backend.reset_mock()
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            ss.push_states(self.run_params, self.env)
            self.backend.unset.assert_not_called()
            self.backend.set.assert_called_once()

        # test push disabled for root/boot states
        self.backend.reset_mock()
        self._set_up_generic_params("push", "root", "objects", "object1")
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            ss.push_states(self.run_params, self.env)
            self.backend.unset.assert_not_called()
            self.backend.set.assert_not_called()
        self.backend.reset_mock()
        self._set_up_generic_params("push", "boot", "objects", "object1")
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            ss.push_states(self.run_params, self.env)
            self.backend.unset.assert_not_called()
            self.backend.set.assert_not_called()

    def test_pop(self):
        """Test that popping with a state backend works."""
        self._set_up_generic_params("pop", "state", "objects", "object1")

        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=True)):
            ss.pop_states(self.run_params, self.env)
            self.backend.get.assert_called_once()
            self.backend.unset.assert_called_once()

        # test pop disabled for root/boot states
        self.backend.reset_mock()
        self._set_up_generic_params("pop", "root", "objects", "object1")
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            ss.pop_states(self.run_params, self.env)
            self.backend.get.assert_not_called()
            self.backend.unset.assert_not_called()
        self.backend.reset_mock()
        self._set_up_generic_params("pop", "root", "objects", "object1")
        with mock.patch('avocado_i2n.states.setup.check_states',
                        mock.MagicMock(return_value=False)):
            ss.pop_states(self.run_params, self.env)
            self.backend.get.assert_not_called()
            self.backend.unset.assert_not_called()

    def test_check_multiobj(self):
        """Test that checking various states of multiple vms and their images works."""
        self._set_up_multiobj_params()
        self.run_params["vms"] = "vm1 vm2"
        self.run_params["images_vm1"] = "image1 image2"
        self.run_params["images_vm2"] = "image21"
        self.run_params["check_state_images"] = "launch"
        self.run_params["check_state_images_image2_vm1"] = "launch2"
        self.run_params["check_state_images_vm2"] = "launcher"
        self.run_params["skip_types"] = "nets"
        self._create_mock_vms()

        self.backend.reset_mock()
        self.backend.show.return_value = ["launch", "launch2", "launcher"]
        exists = ss.check_states(self.run_params, self.env)
        call_params = [call.args[0] for call in self.backend.show.call_args_list]
        self.assertEqual(len(call_params), 3)
        self.assertEqual(call_params[0]["vms"], "vm1")
        self.assertEqual(call_params[0]["images"], "image1")
        self.assertEqual(call_params[0]["object_name"], "net1/vm1/image1")
        self.assertEqual(call_params[0]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[0]["check_state"], "launch")
        self.assertEqual(call_params[1]["vms"], "vm1")
        self.assertEqual(call_params[1]["images"], "image2")
        self.assertEqual(call_params[1]["object_name"], "net1/vm1/image2")
        self.assertEqual(call_params[1]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[1]["check_state"], "launch2")
        self.assertEqual(call_params[2]["vms"], "vm2")
        self.assertEqual(call_params[2]["images"], "image21")
        self.assertEqual(call_params[2]["object_name"], "net1/vm2/image21")
        self.assertEqual(call_params[2]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[2]["check_state"], "launcher")
        self.assertTrue(exists)

        # break on first false state check
        self.backend.reset_mock()
        self.backend.show.side_effect = lambda params, _: params.get("images")
        exists = ss.check_states(self.run_params, self.env)
        call_params = [call.args[0] for call in self.backend.show.call_args_list]
        self.assertEqual(len(call_params), 1)
        self.assertEqual(call_params[0]["vms"], "vm1")
        self.assertEqual(call_params[0]["images"], "image1")
        self.assertEqual(call_params[0]["check_state"], "launch")
        self.assertFalse(exists)

    def test_get_multiobj(self):
        """Test that getting various states of multiple vms and their images works."""
        self._set_up_multiobj_params()
        self.run_params["vms"] = "vm1 vm2 vm3"
        self.run_params["images_vm1"] = "image1 image2"
        self.run_params["get_state_images_vm1"] = "launch1"
        self.run_params["get_state_images_image2_vm1"] = "launch21"
        self.run_params["get_state_images_vm2"] = "launch2"
        self.run_params["get_state_vms_vm3"] = "launch3"
        self.run_params["get_mode"] = "ra"
        self.run_params["get_mode_vm2"] = "ii"
        self.run_params["skip_types"] = "nets"
        self._create_mock_vms()

        self.backend.reset_mock()
        self.backend.show.return_value = ["launch1", "launch2", "launch21", "launch3"]
        ss.get_states(self.run_params, self.env)
        call_params = [call.args[0] for call in self.backend.get.call_args_list]
        self.assertEqual(len(call_params), 3)
        self.assertEqual(call_params[0]["vms"], "vm1")
        self.assertEqual(call_params[0]["images"], "image1")
        self.assertEqual(call_params[0]["object_name"], "net1/vm1/image1")
        self.assertEqual(call_params[0]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[0]["get_state"], "launch1")
        self.assertEqual(call_params[1]["vms"], "vm1")
        self.assertEqual(call_params[1]["images"], "image2")
        self.assertEqual(call_params[1]["object_name"], "net1/vm1/image2")
        self.assertEqual(call_params[1]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[1]["get_state"], "launch21")
        self.assertEqual(call_params[2]["vms"], "vm3")
        self.assertEqual(call_params[2]["object_name"], "net1/vm3")
        self.assertEqual(call_params[2]["object_type"], "nets/vms")
        self.assertEqual(call_params[2]["get_state"], "launch3")

        # break on first false state check with incompatible policy
        self.backend.reset_mock()
        self.backend.show.side_effect = lambda params, _: ["launch1", "launch21"]
        with self.assertRaises(exceptions.TestAbortError):
            ss.get_states(self.run_params, self.env)
        call_params = [call.args[0] for call in self.backend.get.call_args_list]
        self.assertEqual(len(call_params), 2)
        self.assertEqual(call_params[0]["vms"], "vm1")
        self.assertEqual(call_params[0]["images"], "image1")
        self.assertEqual(call_params[0]["get_state"], "launch1")
        self.assertEqual(call_params[1]["vms"], "vm1")
        self.assertEqual(call_params[1]["images"], "image2")
        self.assertEqual(call_params[1]["get_state"], "launch21")

    def test_set_multiobj(self):
        """Test that setting various states of multiple vms and their images works."""
        self._set_up_multiobj_params()
        self.run_params["vms"] = "vm2 vm3 vm4"
        self.run_params["images_vm2"] = "image21 image22"
        self.run_params["set_state_images_vm2"] = "launch2"
        self.run_params["set_state_images_image22_vm2"] = "launch22"
        self.run_params["set_state_images_vm3"] = "launch3"
        self.run_params["set_state_vms_vm4"] = "launch4"
        self.run_params["set_mode"] = "fa"
        self.run_params["set_mode_vm3"] = "ff"
        self.run_params["skip_types"] = "nets"
        self._create_mock_vms()

        self.backend.reset_mock()
        self.backend.show.return_value = ["launch2", "launch22", "launch3", "launch4"]
        ss.set_states(self.run_params, self.env)
        call_params = [call.args[0] for call in self.backend.set.call_args_list]
        self.assertEqual(len(call_params), 4)
        self.assertEqual(call_params[0]["vms"], "vm2")
        self.assertEqual(call_params[0]["images"], "image21")
        self.assertEqual(call_params[0]["object_name"], "net1/vm2/image21")
        self.assertEqual(call_params[0]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[0]["set_state"], "launch2")
        self.assertEqual(call_params[1]["vms"], "vm2")
        self.assertEqual(call_params[1]["images"], "image22")
        self.assertEqual(call_params[1]["object_name"], "net1/vm2/image22")
        self.assertEqual(call_params[1]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[1]["set_state"], "launch22")
        self.assertEqual(call_params[2]["vms"], "vm3")
        self.assertEqual(call_params[2]["object_name"], "net1/vm3/image1")
        self.assertEqual(call_params[2]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[2]["set_state"], "launch3")
        self.assertEqual(call_params[3]["vms"], "vm4")
        self.assertEqual(call_params[3]["object_name"], "net1/vm4")
        self.assertEqual(call_params[3]["object_type"], "nets/vms")
        self.assertEqual(call_params[3]["set_state"], "launch4")

        # break on first false state check with incompatible policy
        self.backend.reset_mock()
        self.backend.show.return_value = ["launch2", "launch22"]
        with self.assertRaises(exceptions.TestAbortError):
            ss.set_states(self.run_params, self.env)
        call_params = [call.args[0] for call in self.backend.set.call_args_list]
        self.assertEqual(len(call_params), 3)
        self.assertEqual(call_params[0]["vms"], "vm2")
        self.assertEqual(call_params[0]["images"], "image21")
        self.assertEqual(call_params[0]["set_state"], "launch2")
        self.assertEqual(call_params[1]["vms"], "vm2")
        self.assertEqual(call_params[1]["images"], "image22")
        self.assertEqual(call_params[1]["set_state"], "launch22")
        self.assertEqual(call_params[2]["vms"], "vm3")
        self.assertEqual(call_params[2]["object_name"], "net1/vm3/image1")
        self.assertEqual(call_params[2]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[2]["set_state"], "launch3")

    def test_unset_multiobj(self):
        """Test that unsetting various states of multiple vms and their images works."""
        self._set_up_multiobj_params()
        self.run_params["vms"] = "vm1 vm4"
        self.run_params["images_vm1"] = "image1 image2"
        self.run_params["unset_state_images_vm1"] = "launch1"
        self.run_params["unset_state_images_image2_vm1"] = "launch2"
        self.run_params["unset_state_images_vm4"] = "launch4"
        self.run_params["unset_mode_vm1"] = "fi"
        self.run_params["unset_mode_vm4"] = "fa"
        self.run_params["skip_types"] = "nets"
        self._create_mock_vms()

        self.backend.reset_mock()
        self.backend.show.return_value = ["launch1", "launch2", "launch4"]
        ss.unset_states(self.run_params, self.env)
        call_params = [call.args[0] for call in self.backend.unset.call_args_list]
        self.assertEqual(len(call_params), 3)
        self.assertEqual(call_params[0]["vms"], "vm1")
        self.assertEqual(call_params[0]["images"], "image1")
        self.assertEqual(call_params[0]["object_name"], "net1/vm1/image1")
        self.assertEqual(call_params[0]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[0]["unset_state"], "launch1")
        self.assertEqual(call_params[1]["vms"], "vm1")
        self.assertEqual(call_params[1]["images"], "image2")
        self.assertEqual(call_params[1]["object_name"], "net1/vm1/image2")
        self.assertEqual(call_params[1]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[1]["unset_state"], "launch2")
        self.assertEqual(call_params[2]["vms"], "vm4")
        self.assertEqual(call_params[2]["object_name"], "net1/vm4/image1")
        self.assertEqual(call_params[2]["object_type"], "nets/vms/images")
        self.assertEqual(call_params[2]["unset_state"], "launch4")

        self.backend.reset_mock()
        self.backend.show.return_value = []
        with self.assertRaises(exceptions.TestAbortError):
            ss.unset_states(self.run_params, self.env)
        call_params = [call.args[0] for call in self.backend.unset.call_args_list]
        self.assertEqual(len(call_params), 0)

    def test_skip_type(self):
        """Test that given state types are skipped via a devoted parameter."""
        self._set_up_generic_params("pop", "state", "objects", "object1")
        self.run_params["skip_types"] = "objects"

        for do in ["check", "get", "set", "unset"]:
            with self.subTest(f"Testing state type skipping for {do}"):
                self.run_params[f"{do}_state"] = "launch"

                ss.__dict__[f"{do}_states"](self.run_params, self.env)
                self.assertEqual(len(self.backend.__dict__["_mock_children"]), 0)


if __name__ == '__main__':
    unittest.main()
