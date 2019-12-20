import unittest
import logging

try:
    from unittest import mock
except ImportError:
    import mock

from virttest.utils_test import update_boot_option
from virttest import utils_test
from avocado.core import exceptions

check_kernel_cmdline_mock = mock.MagicMock(return_value=["3", None])


@mock.patch('virttest.utils_package.package_install')
@mock.patch.object(utils_test, 'check_kernel_cmdline', check_kernel_cmdline_mock)
class TestUpdateBootOptionZipl(unittest.TestCase):
    vm = mock.MagicMock()
    session = mock.MagicMock()

    # login_timeout
    vm.params.get.return_value = "0"

    # mocked session, always succeed
    vm.wait_for_login.return_value = session
    session.cmd_status_output.return_value = [0, ""]

    def tearDown(self):
        check_kernel_cmdline_mock.reset_mock()
        self.session.cmd_status_output.reset_mock()

    def test_args_no_zipl(self, *mocks):
        update_boot_option(self.vm, args_added="3", need_reboot=False)
        utils_test.check_kernel_cmdline.assert_called_once()
        self.session.cmd_status_output.assert_called_once()

    def test_args_zipl(self, *mocks):
        update_boot_option(self.vm, args_added="3", need_reboot=False, guest_arch_name="s390x")
        utils_test.check_kernel_cmdline.assert_called_once()
        self.assertEqual(2, self.session.cmd_status_output.call_count)

    # Test error handling for session.cmd_status_output
    some_error_message = "some error"

    @mock.patch.object(utils_test.logging, 'error')
    def test_cmd_fail(self, *mocks):
        self.session.cmd_status_output.return_value = [1, self.some_error_message]

        with self.assertRaises(exceptions.TestError) as e:
            update_boot_option(self.vm, args_added="3", need_reboot=False)
        self.assertIsNotNone(e.exception.args[0])
        logging.error.assert_called_with(self.some_error_message)


if __name__ == '__main__':
    unittest.main()
