#!/usr/bin/python
import os
import sys
import unittest

from avocado import Test
from avocado.utils import path, process
from avocado.utils.process import CmdResult

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, "virttest")):
    sys.path.append(basedir)

from virttest import iscsi, utils_package, utils_selinux
from virttest.unittest_utils import mock


class iscsi_test(Test):
    def setup_stubs_init(self):
        pass

    def setup_stubs_login(self, iscsi_obj):
        c_cmd = "dd if=/dev/zero of=/tmp/iscsitest count=1024 bs=1K"
        lg_cmd = "iscsiadm --mode node --login --targetname "
        lg_cmd += "%s" % iscsi_obj.target
        lg_cmd += " --portal %s" % iscsi_obj.portal_ip
        self.setup_stubs_portal_visible(iscsi_obj)
        os.path.isfile.expect_call(iscsi_obj.emulated_image).and_return(False)
        process.system.expect_call(c_cmd)
        self.setup_stubs_export_target(iscsi_obj)
        self.setup_stubs_portal_visible(
            iscsi_obj, "127.0.0.1:3260,1 %s" % iscsi_obj.target
        )

    def setup_stubs_get_device_name(self, iscsi_obj):
        s_msg = "tcp: [15] 127.0.0.1:3260,1 %s" % iscsi_obj.target
        self.session_output = s_msg
        detail = "Target: %s\n Attached scsi disk " % iscsi_obj.target
        detail += "sdb State running"
        self.session_detail = detail

    def setup_stubs_cleanup(self, iscsi_obj, fname=""):
        self.session_output = "tcp [15] 127.0.0.1:3260,1 %s" % iscsi_obj.target
        self.node_output = "127.0.0.1:3260,1 %s" % iscsi_obj.target
        out_cmd = "iscsiadm -m node -o delete -T %s " % iscsi_obj.target
        out_cmd += "--portal 127.0.0.1"
        process.system.expect_call(out_cmd, ignore_status=True).and_return("")
        d_cmd = "targetcli /iscsi delete %s" % iscsi_obj.target
        process.system.expect_call(d_cmd)
        cmd = "targetcli / saveconfig"
        process.system.expect_call(cmd)

    def setup_stubs_logged_in(self, result=""):
        self.session_output = result

    def setup_stubs_portal_visible(self, iscsi_obj, result=""):
        self.discovery_outputs.append(result)

    def setup_stubs_export_target(self, iscsi_obj):
        utils_selinux.is_enforcing.expect_call().and_return(False)
        cmd = "firewall-cmd --permanent --add-port=3260/tcp"
        process.system.expect_call(cmd)
        cmd = "firewall-cmd --reload"
        process.system.expect_call(cmd)
        self.setup_stubs_set_chap_auth_target(iscsi_obj)
        self.setup_stubs_portal_visible(
            iscsi_obj, "127.0.0.1:3260,1 %s" % iscsi_obj.target
        )
        self.setup_stubs_set_chap_auth_initiator(iscsi_obj)
        cmd = "targetcli / saveconfig"
        process.system.expect_call(cmd)

    def setup_stubs_get_target_id(self, iscsi_obj):
        self.target_info = (
            "o- iscsi ... [Targets: 1]\no- %s ... [TPGs: 1]" % iscsi_obj.target
        )
        self.luns_info = "o- lun0 [%s]" % iscsi_obj.emulated_image

    def setup_stubs_get_chap_accounts(self, result=""):
        s_cmd = "tgtadm --lld iscsi --op show --mode account"
        process.system_output.expect_call(s_cmd).and_return(result)

    def setup_stubs_add_chap_account(self, iscsi_obj):
        n_cmd = "tgtadm --lld iscsi --op new --mode account"
        n_cmd += " --user %s" % iscsi_obj.chap_user
        n_cmd += " --password %s" % iscsi_obj.chap_passwd
        process.system.expect_call(n_cmd)
        a_msg = "Account list:\n %s" % iscsi_obj.chap_user
        self.setup_stubs_get_chap_accounts(a_msg)

    def setup_stubs_get_target_account_info(self):
        s_cmd = "tgtadm --lld iscsi --mode target --op show"
        s_msg = "Target 1: iqn.iscsitest\nAccount information:\n"
        process.system_output.expect_call(s_cmd).and_return(s_msg)

    def setup_stubs_set_chap_auth_target(self, iscsi_obj):
        comm_cmd = "targetcli /iscsi/%s/tpg1/ " % iscsi_obj.target
        cmd = "%sset attribute demo_mode_write_protect=0 " % comm_cmd
        cmd += "generate_node_acls=1 cache_dynamic_acls=1"
        process.system.expect_call(cmd)
        cmd = "targetcli / saveconfig"
        process.system.expect_call(cmd)

    def setup_stubs_set_chap_auth_initiator(self, iscsi_obj):
        u_name = {"node.session.auth.authmethod": "CHAP"}
        u_name["node.session.auth.username"] = iscsi_obj.chap_user
        u_name["node.session.auth.password"] = iscsi_obj.chap_passwd
        for name in list(u_name.keys()):
            u_cmd = "iscsiadm --mode node --targetname %s " % iscsi_obj.target
            u_cmd += "--op update --name %s --value %s" % (name, u_name[name])
            process.system.expect_call(u_cmd)

    def setUp(self):
        # The normal iscsi with iscsi server should configure following
        # parameters. As this will need env support only test emulated
        # iscsi in local host.
        # self.iscsi_params = {"target": "",
        #                       "portal_ip": "",
        #                       "initiator": ""}

        self.iscsi_emulated_params = {
            "emulated_image": "/tmp/iscsitest",
            "target": "iqn.2003-01.org.linux:iscsitest",
            "image_size": "1024K",
            "chap_user": "tester",
            "chap_passwd": "123456",
        }
        self.god = mock.mock_god()
        self.god.stub_function(path, "find_command")
        self.god.stub_function(process, "system")
        self.god.stub_function(process, "system_output")
        self.god.stub_with(process, "run", self._process_run)
        self.god.stub_function(os.path, "isfile")
        self.god.stub_function(utils_selinux, "is_enforcing")
        self.god.stub_with(
            utils_package, "package_install", lambda *args, **kwargs: True
        )
        self.session_output = "No active sessions"
        self.session_detail = ""
        self.node_output = ""
        self.discovery_outputs = []
        self.target_info = ""
        self.luns_info = ""

    def _process_run(self, cmd, *args, **kwargs):
        if cmd == "iscsiadm --mode session":
            stdout = self.session_output
        elif cmd == "iscsiadm -m session -P 3":
            stdout = self.session_detail
        elif cmd.startswith("iscsiadm -m discovery"):
            if self.discovery_outputs:
                stdout = self.discovery_outputs.pop(0)
            else:
                stdout = ""
        elif cmd.startswith("iscsiadm --mode node --login"):
            stdout = "successful"
            self.session_output = (
                "tcp: [15] 127.0.0.1:3260,1 %s" % self.iscsi_emulated_params["target"]
            )
        elif cmd.startswith("iscsiadm --mode node --logout"):
            stdout = "successful"
            self.session_output = "No active sessions"
        elif cmd == "iscsiadm --mode node":
            stdout = self.node_output
        elif cmd == "targetcli ls /iscsi 1":
            stdout = self.target_info
        elif cmd == "targetcli /backstores/fileio ls":
            stdout = "Target 1: iqn.iscsitest"
        elif cmd.endswith("/tpg1/luns"):
            stdout = self.luns_info
        elif "/backstores/fileio/ create" in cmd:
            stdout = "Created fileio"
        elif cmd.startswith("targetcli /iscsi/ create"):
            stdout = "Created target"
            self.target_info = (
                "o- iscsi ... [Targets: 1]\no- %s ... [TPGs: 1]"
                % self.iscsi_emulated_params["target"]
            )
        elif cmd.endswith("/tpg1/portals ls"):
            stdout = "0.0.0.0:3260"
        elif "/tpg1/luns/" in cmd and " create " in cmd:
            stdout = "Created LUN 0."
            self.luns_info = (
                "o- lun0 [%s]" % self.iscsi_emulated_params["emulated_image"]
            )
        elif cmd == "firewall-cmd --state":
            stdout = "running"
        elif " set auth userid=" in cmd:
            stdout = self.iscsi_emulated_params["chap_user"]
        elif " set auth password=" in cmd:
            stdout = self.iscsi_emulated_params["chap_passwd"]
        else:
            stdout = ""
        return CmdResult(cmd, stdout=stdout)

    def tearDown(self):
        self.god.unstub_all()

    def test_iscsi_get_device_name(self):
        self.setup_stubs_init()
        iscsi_emulated = iscsi.Iscsi.create_iSCSI(self.iscsi_emulated_params)
        iscsi_emulated.emulated_id = "1"
        self.setup_stubs_login(iscsi_emulated)
        iscsi_emulated.login()
        self.setup_stubs_get_device_name(iscsi_emulated)
        self.assertNotEqual(iscsi_emulated.get_device_name(), "")
        self.setup_stubs_cleanup(iscsi_emulated)
        iscsi_emulated.cleanup()

    def test_iscsi_login(self):
        self.setup_stubs_init()
        iscsi_emulated = iscsi.Iscsi.create_iSCSI(self.iscsi_emulated_params)
        self.setup_stubs_logged_in()
        self.assertFalse(iscsi_emulated.logged_in())
        result = "tcp [15] 127.0.0.1:3260,1 %s" % iscsi_emulated.target
        self.setup_stubs_logged_in(result)
        self.assertTrue(iscsi_emulated.logged_in())

    def test_iscsi_visible(self):
        self.setup_stubs_init()
        iscsi_emulated = iscsi.Iscsi.create_iSCSI(self.iscsi_emulated_params)
        self.setup_stubs_portal_visible(iscsi_emulated)
        self.assertFalse(iscsi_emulated.portal_visible())
        self.setup_stubs_portal_visible(
            iscsi_emulated, "127.0.0.1:3260,1 %s" % iscsi_emulated.target
        )

    def test_iscsi_target_id(self):
        self.setup_stubs_init()
        iscsi_emulated = iscsi.Iscsi.create_iSCSI(self.iscsi_emulated_params)
        self.setup_stubs_get_target_id(iscsi_emulated)
        self.assertNotEqual(iscsi_emulated.get_target_id(), "")


if __name__ == "__main__":
    unittest.main()
