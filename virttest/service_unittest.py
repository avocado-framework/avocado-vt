#!/usr/bin/env python
import unittest

import common
from autotest.client import utils
from autotest.client.shared.mock import MagicMock, patch

import staging.service as service


class ConstantsTest(unittest.TestCase):

    def test_ModuleLoad(self):
        self.assertTrue(hasattr(service, 'COMMANDS'))


class SystemdGeneratorTest(unittest.TestCase):

    def setUp(self):
        helper = service.Factory.FactoryHelper()
        helper.init_name = "systemd"
        self.service_name = "fake_service"
        self.cmd_generator = helper.get_generic_service_command_generator()
        self.assertTrue(isinstance(self.cmd_generator,
                                   service._ServiceCommandGenerator))

    def test_all_command(self):
        self.assertTrue(hasattr(self.cmd_generator, 'commands'))
        for cmd in self.cmd_generator.commands:
            self.assertTrue(hasattr(self.cmd_generator, cmd))
            ret = getattr(self.cmd_generator, cmd)(self.service_name)
            if cmd not in ["list", "set_target"]:
                if cmd == "is_enabled":
                    cmd = "is-enabled"
                elif cmd == "reset_failed":
                    cmd = "reset-failed"
                elif cmd == "raw_status":
                    cmd = "status"
                assert ret == ["systemctl", cmd, "%s.service" % self.service_name]

    def test_list(self):
        ret = getattr(self.cmd_generator, 'list')(self.service_name)
        assert ret == ["systemctl", "list-unit-files", "--type=service",
                       "--no-pager", "--full"]

    def test_set_target(self):
        ret = getattr(self.cmd_generator, 'set_target')("multi-user.target")
        assert ret == ["systemctl", "isolate", "multi-user.target"]


class SysVInitGeneratorTest(unittest.TestCase):

    def setUp(self):
        helper = service.Factory.FactoryHelper()
        helper.init_name = "init"
        self.service_name = "fake_service"
        self.cmd_generator = helper.get_generic_service_command_generator()
        self.assertTrue(isinstance(self.cmd_generator,
                                   service._ServiceCommandGenerator))

    def test_all_command(self):
        self.assertTrue(hasattr(self.cmd_generator, 'commands'))
        for cmd in self.cmd_generator.commands:
            self.assertTrue(hasattr(self.cmd_generator, cmd))
            if cmd not in ["list", "set_target", "reset_failed"]:
                ret = getattr(self.cmd_generator, cmd)(self.service_name)
                command_name = "service"
                if cmd == "is_enabled":
                    command_name = "chkconfig"
                    cmd = ""
                elif cmd == "enable":
                    command_name = "chkconfig"
                    cmd = "on"
                elif cmd == "disable":
                    command_name = "chkconfig"
                    cmd = "off"
                elif cmd == "raw_status":
                    cmd = "status"
                assert ret == [command_name, self.service_name, cmd]

    def test_set_target(self):
        ret = getattr(self.cmd_generator, "set_target")("multi-user.target")
        assert ret == ["telinit", "3"]


class ResultParserTest(unittest.TestCase):

    def test_systemd_result_parser(self):
        helper = service.Factory.FactoryHelper()
        helper.init_name = "systemd"
        result_parser = helper.get_generic_service_result_parser()
        self.assertTrue(isinstance(result_parser,
                                   service._ServiceResultParser))
        self.assertTrue(hasattr(result_parser, 'commands'))
        for cmd in result_parser.commands:
            self.assertTrue(hasattr(result_parser, cmd))
        # here just check status and list
        self.assertEqual(result_parser.status,
                         service.systemd_status_parser)
        self.assertEqual(result_parser.list,
                         service.systemd_list_parser)
        del result_parser
        del helper

    def test_sysvinit_result_parser(self):
        helper = service.Factory.FactoryHelper()
        helper.init_name = "init"
        result_parser = helper.get_generic_service_result_parser()
        self.assertTrue(isinstance(result_parser,
                                   service._ServiceResultParser))
        self.assertTrue(hasattr(result_parser, 'commands'))
        for cmd in result_parser.commands:
            self.assertTrue(hasattr(result_parser, cmd))
        # here just check status and list
        self.assertEqual(result_parser.status,
                         service.sysvinit_status_parser)
        self.assertEqual(result_parser.list,
                         service.sysvinit_list_parser)
        del result_parser
        del helper


class TestServiceManager(object):

    def __init__(self, init_name, run_mock):
        self.helper = service.Factory.FactoryHelper()
        self.helper.init_name = init_name
        self.helper.run = run_mock

    def get_service_manager(self):
        service_manager = self.helper.get_generic_service_manager_type()
        # get command generator and result parser
        command_generator = self.helper.get_generic_service_command_generator()
        result_parser = self.helper.get_generic_service_result_parser()
        return service_manager(command_generator, result_parser, self.helper.run)


class TestSystemdServiceManager(unittest.TestCase):

    def setUp(self):
        self.run_mock = MagicMock()
        self.init_name = "systemd"

    def test_start(self):
        service = "lldpad"
        service_manager = TestServiceManager(self.init_name,
                                             self.run_mock).get_service_manager()
        service_manager.start(service)
        assert self.run_mock.call_args[0][
            0] == "systemctl start %s.service" % service
        del service_manager

    def test_list(self):
        list_result_mock = MagicMock(exit_status=0, stdout="sshd.service enabled\n"
                                                           "vsftpd.service disabled\n"
                                                           "systemd-sysctl.service static\n")
        run_mock = MagicMock(return_value=list_result_mock)
        service_manager = TestServiceManager(self.init_name,
                                             run_mock).get_service_manager()
        list_result = service_manager.list(ignore_status=False)
        assert run_mock.call_args[0][
            0] == "systemctl list-unit-files --type=service --no-pager --full"
        assert list_result == {'sshd': "enabled",
                               'vsftpd': "disabled",
                               'systemd-sysctl': "static"}


class TestSysVInitServiceManager(unittest.TestCase):

    def setUp(self):
        self.run_mock = MagicMock()
        self.init_name = "init"

    def test_list(self):
        list_result_mock = MagicMock(exit_status=0,
                                     stdout="sshd             0:off   1:off   2:off   3:off   4:off   5:off   6:off\n"
                                            "vsftpd           0:off   1:off   2:off   3:off   4:off   5:on   6:off\n"
                                            "xinetd based services:\n"
                                            "        amanda:         off\n"
                                            "        chargen-dgram:  on\n")

        run_mock = MagicMock(return_value=list_result_mock)
        service_manager = TestServiceManager(self.init_name,
                                             run_mock).get_service_manager()
        list_result = service_manager.list(ignore_status=False)
        assert run_mock.call_args[0][
            0] == "chkconfig --list"
        assert list_result == {'sshd': {0: "off", 1: "off", 2: "off", 3: "off", 4: "off", 5: "off", 6: "off"},
                               'vsftpd': {0: "off", 1: "off", 2: "off", 3: "off", 4: "off", 5: "on", 6: "off"},
                               'xinetd': {'amanda': "off", 'chargen-dgram': "on"}}

    def test_enable(self):
        service = "lldpad"
        service_manager = TestServiceManager(self.init_name,
                                             self.run_mock).get_service_manager()
        service_manager.enable(service)
        assert self.run_mock.call_args[0][0] == "chkconfig lldpad on"

    def test_unknown_runlevel(self):
        self.assertRaises(ValueError,
                          service.convert_sysv_runlevel, "unknown")

    def test_runlevels(self):
        assert service.convert_systemd_target_to_runlevel(
            "poweroff.target") == '0'
        assert service.convert_systemd_target_to_runlevel(
            "rescue.target") == 's'
        assert service.convert_systemd_target_to_runlevel(
            "multi-user.target") == '3'
        assert service.convert_systemd_target_to_runlevel(
            "graphical.target") == '5'
        assert service.convert_systemd_target_to_runlevel(
            "reboot.target") == '6'


if __name__ == '__main__':
    unittest.main()
