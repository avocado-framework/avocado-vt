import unittest
import uuid
import os.path

try:
    from unittest import mock
except ImportError:
    import mock

from virttest import utils_kernel_module

some_module_name = 'skvm'
some_module_param = 'force_emulation_prefix'
some_module_val = 'N'
some_module_config = {some_module_param: 'N',
                      'halt_poll_ns_shrink': '0'}

getstatusoutput_ok = mock.Mock(return_value=(0, ""))


class TestModuleInfo(unittest.TestCase):
    @mock.patch.object(utils_kernel_module.os.path, 'exists', return_value=False)
    def test__load_config_module_not_loaded(self, *mocks):
        kvm_config = utils_kernel_module.KernelModuleHandler._load_config(some_module_name)
        self.assertIs(None, kvm_config)

    @mock.patch.object(utils_kernel_module.os.path, 'exists', return_value=True)
    @mock.patch.object(utils_kernel_module.os, 'listdir', return_value=[some_module_param])
    @mock.patch.object(utils_kernel_module, 'open', mock.mock_open(read_data=some_module_val + '\n'))
    def test__load_config_module_loaded(self, *mocks):
        kvm_config = utils_kernel_module.KernelModuleHandler._load_config(some_module_name)
        self.assertEqual(1, len(kvm_config))
        first = list(kvm_config.items())[0]
        self.assertEqual(some_module_param, first[0])
        self.assertEqual(some_module_val, first[1])


@mock.patch.object(utils_kernel_module.os.path, 'exists', return_value=True)
@mock.patch.object(utils_kernel_module.os, 'listdir', return_value=[some_module_param])
@mock.patch.object(utils_kernel_module, 'open', mock.mock_open(read_data=some_module_val + '\n'))
class TestKernelModuleLoaded(unittest.TestCase):

    def test_instance_backs_up(self, *mocks):
        handler = utils_kernel_module.KernelModuleHandler(some_module_name)
        self.assertIsNotNone(handler._config_backup)
        self.assertTrue(handler._was_loaded)
        self.assertEqual("force_emulation_prefix=N", handler._config_backup)

    pickle_dump = mock.MagicMock()
    pickle_load = mock.MagicMock()
    remove_file = mock.MagicMock()

    @mock.patch.object(utils_kernel_module.pickle, 'dump', pickle_dump)
    @mock.patch.object(utils_kernel_module.pickle, 'load', pickle_load)
    @mock.patch.object(utils_kernel_module.os.path, 'isfile', return_value=False)
    def test_instance_persistence_not_existing(self, *mocks):
        persistence_file = os.path.join('/tmp/', str(uuid.uuid4()))
        handler = utils_kernel_module.KernelModuleHandler(some_module_name, persistence_file)
        self.pickle_load.assert_not_called()
        handler.save()
        self.pickle_dump.assert_called_once()

    @mock.patch.object(utils_kernel_module.pickle, 'dump', pickle_dump)
    @mock.patch.object(utils_kernel_module.pickle, 'load', pickle_load)
    @mock.patch.object(utils_kernel_module.os.path, 'isfile', return_value=True)
    def test_instance_persistence_existing(self, *mocks):
        persistence_file = os.path.join('/tmp/', str(uuid.uuid4()))
        handler = utils_kernel_module.KernelModuleHandler(some_module_name, persistence_file)
        self.pickle_load.assert_called_once()

    @mock.patch.object(utils_kernel_module.pickle, 'dump', pickle_dump)
    @mock.patch.object(utils_kernel_module.process, 'getstatusoutput', getstatusoutput_ok)
    @mock.patch.object(utils_kernel_module.os.path, 'isfile', return_value=False)
    def test_load_module_persists_itself_by_default(self, *mocks):
        persistence_file = os.path.join('/tmp/', str(uuid.uuid4()))
        handler = utils_kernel_module.KernelModuleHandler(some_module_name, persistence_file)
        handler.load_module(params="key=value")
        self.pickle_dump.assert_called_once()

    @mock.patch.object(utils_kernel_module.process, 'getstatusoutput', getstatusoutput_ok)
    def test_load_module(self, *mocks):
        handler = utils_kernel_module.KernelModuleHandler('skvm')
        handler.load_module(params="key=value")
        getstatusoutput_ok.assert_called_with('rmmod skvm; modprobe skvm key=value',
                                              ignore_status=True, shell=True)

    @mock.patch.object(utils_kernel_module.process, 'getstatusoutput', getstatusoutput_ok)
    def test_load_module_twice_same_params(self, *mocks):
        handler = utils_kernel_module.KernelModuleHandler('skvm')
        handler.load_module(params="key=value")
        getstatusoutput_ok.reset_mock()
        handler.load_module(params="key=value")
        getstatusoutput_ok.assert_not_called()

    @mock.patch.object(utils_kernel_module.process, 'getstatusoutput', getstatusoutput_ok)
    def test_load_module_twice_different_params(self, *mocks):
        handler = utils_kernel_module.KernelModuleHandler('skvm')
        handler.load_module(params="key=value")
        getstatusoutput_ok.reset_mock()
        handler.load_module(params="key=value1")
        getstatusoutput_ok.assert_called_with('rmmod skvm; modprobe skvm key=value1',
                                              ignore_status=True, shell=True)

    @mock.patch.object(utils_kernel_module.process, 'getstatusoutput', getstatusoutput_ok)
    def test_load_module_twice_restore(self, *mocks):
        handler = utils_kernel_module.KernelModuleHandler(some_module_name)
        handler.load_module(params="key=value")
        handler.load_module(params="key=value1")
        handler.restore()
        cmd = getstatusoutput_ok.call_args[0][0]
        self.assertTrue(some_module_param in cmd)

    @mock.patch.object(utils_kernel_module.process, 'getstatusoutput', getstatusoutput_ok)
    @mock.patch.object(utils_kernel_module.KernelModuleHandler, '_load_config', return_value=some_module_config)
    def test_restore(self, *mocks):
        handler = utils_kernel_module.KernelModuleHandler(some_module_name)
        handler.load_module(params="key=value")
        handler.restore()
        cmd = getstatusoutput_ok.call_args[0][0]
        self.assertTrue(some_module_param in cmd)

    @mock.patch.object(utils_kernel_module.process, 'getstatusoutput', getstatusoutput_ok)
    @mock.patch.object(utils_kernel_module.KernelModuleHandler, '_load_config', return_value=some_module_config)
    def test_restore_only_if_updated_config(self, *mocks):
        handler = utils_kernel_module.KernelModuleHandler(some_module_name)
        getstatusoutput_ok.reset_mock()
        handler.restore()
        getstatusoutput_ok.assert_not_called()

    @mock.patch.object(utils_kernel_module.pickle, 'dump', pickle_dump)
    @mock.patch.object(utils_kernel_module.pickle, 'load', pickle_load)
    @mock.patch.object(utils_kernel_module.os.path, 'isfile', return_value=True)
    @mock.patch.object(utils_kernel_module.os, 'remove', remove_file)
    @mock.patch.object(utils_kernel_module.process, 'getstatusoutput', getstatusoutput_ok)
    @mock.patch.object(utils_kernel_module.KernelModuleHandler, '_load_config', return_value=some_module_config)
    def test_restore_removes_persistence_file_per_default(self, *mocks):
        persistence_file = os.path.join('/tmp/', str(uuid.uuid4()))
        handler = utils_kernel_module.KernelModuleHandler(some_module_name, persistence_file)
        handler._loaded_config = "key=value"
        handler.restore()
        self.remove_file.assert_called_once()

    def tearDown(self):
        getstatusoutput_ok.reset_mock()
        self.pickle_load.reset_mock()
        self.pickle_dump.reset_mock()


@mock.patch.object(utils_kernel_module.os.path, 'exists', return_value=False)
class TestModuleNotLoaded(unittest.TestCase):

    def test_instance_stores_not_loaded(self, *mocks):
        handler = utils_kernel_module.KernelModuleHandler(some_module_name)
        self.assertFalse(handler._was_loaded)

    @mock.patch.object(utils_kernel_module.process, 'getstatusoutput', getstatusoutput_ok)
    def test_load_not_forced(self, *mocks):
        handler = utils_kernel_module.KernelModuleHandler(some_module_name)
        handler.load_module(force=False)
        self.assertFalse(getstatusoutput_ok.assert_not_called())

    @mock.patch.object(utils_kernel_module.process, 'getstatusoutput', getstatusoutput_ok)
    def test_load_is_forced(self, *mocks):
        handler = utils_kernel_module.KernelModuleHandler(some_module_name)
        handler.load_module(params="key1=val1")
        cmd = getstatusoutput_ok.call_args[0][0]
        self.assertTrue("key1" in cmd)

    def tearDown(self):
        getstatusoutput_ok.reset_mock()


if __name__ == '__main__':
    unittest.main()
