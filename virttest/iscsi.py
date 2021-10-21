"""
Basic iscsi support for Linux host with the help of commands
iscsiadm and tgtadm.

This include the basic operates such as login and get device name by
target name. And it can support the real iscsi access and emulated
iscsi in localhost then access it.
"""

from __future__ import division
import re
import os
import logging

from avocado.core import exceptions
from avocado.utils import data_factory
from avocado.utils import process
from avocado.utils import path
from avocado.utils import distro

from virttest import utils_selinux
from virttest import utils_net
from virttest import data_dir
from virttest import utils_package
from virttest.staging import service

LOG = logging.getLogger('avocado.' + __name__)

ISCSI_CONFIG_FILE = "/etc/iscsi/initiatorname.iscsi"


def get_image_filename(portal, target, lun=0, user=None, password=None):
    """
    Form the iscsi image name, now only tcp is supported by qemu
    e.g. iscsi://10.66.10.26/iqn.2019-09.com.example:zhencliu/0
    """
    uri = 'iscsi://{auth}{portal}/{target}/{lun}'
    auth = '{user}:{password}@'.format(
        user=user, password=password) if user and password else ''
    return uri.format(auth=auth, portal=portal, target=target, lun=lun)


def restart_iscsid(reset_failed=True):
    """
    Restart iscsid service.
    """
    path.find_command('iscsid')
    iscsid = service.Factory.create_service('iscsid')
    if reset_failed:
        iscsid.reset_failed()
    if not iscsid.restart():
        return False
    else:
        # Make sure exist connection is operational after recovery
        process.run('iscsiadm -m node --rescan', timeout=30,
                    verbose=False, ignore_status=True,
                    shell=True)
        return True


def restart_tgtd(reset_failed=True):
    """
    Restart tgtd service.
    """
    path.find_command('tgtd')
    tgtd = service.Factory.create_service('tgtd')
    if reset_failed:
        tgtd.reset_failed()
    if not tgtd.restart():
        return False
    return True


def iscsi_get_sessions():
    """
    Get the iscsi sessions activated
    """
    cmd = "iscsiadm --mode session"

    output = process.run(cmd, ignore_status=True).stdout_text
    sessions = []
    if "No active sessions" not in output:
        for session in output.splitlines():
            ip_addr = session.split()[2].split(',')[0]
            target = session.split()[3]
            sessions.append((ip_addr, target))
    return sessions


def iscsi_get_nodes():
    """
    Get the iscsi nodes
    """
    cmd = "iscsiadm --mode node"

    output = process.run(cmd, ignore_status=True).stdout_text
    pattern = r"(\d+\.\d+\.\d+\.\d+|\[.+\]):\d+,\d+\s+([\w\.\-:\d]+)"
    nodes = []
    if "No records found" not in output:
        nodes = re.findall(pattern, output)
    return nodes


def iscsi_login(target_name, portal):
    """
    Login to a target with the target name

    :param target_name: Name of the target
    :params portal: Hostname/Ip for iscsi server
    """
    cmd = "iscsiadm --mode node --login --targetname %s" % target_name
    cmd += " --portal %s" % portal
    output = process.run(cmd).stdout_text

    target_login = ""
    if "successful" in output:
        target_login = target_name

    return target_login


def iscsi_node_del(target_name=None):
    """
    Delete target node record, if the target name is not set then delete
    all target node records.

    :params target_name: Name of the target.
    """
    node_list = iscsi_get_nodes()
    cmd = ''
    if target_name:
        for node_tup in node_list:
            if target_name in node_tup:
                cmd = "iscsiadm -m node -o delete -T %s " % target_name
                cmd += "--portal %s" % node_tup[0]
                process.system(cmd, ignore_status=True)
                break
        if not cmd:
            LOG.error("The target '%s' for delete is not in target node"
                      " record", target_name)
    else:
        for node_tup in node_list:
            cmd = "iscsiadm -m node -o delete -T %s " % node_tup[1]
            cmd += "--portal %s" % node_tup[0]
            process.system(cmd, ignore_status=True)


def iscsi_logout(target_name=None):
    """
    Logout from a target. If the target name is not set then logout all
    targets.

    :params target_name: Name of the target.
    """
    if target_name:
        cmd = "iscsiadm --mode node --logout -T %s" % target_name
    else:
        cmd = "iscsiadm --mode node --logout all"

    output = ''
    try:
        output = process.run(cmd).stdout_text
    except process.CmdError as detail:
        # iscsiadm will fail when no matching sessions found
        # This failure makes no sense when target name is not specified
        stderr = detail.result.stderr_text
        if not target_name and 'No matching sessions' in stderr:
            LOG.info("%s: %s", detail, stderr)
        else:
            raise

    target_logout = ""
    if "successful" in output:
        target_logout = target_name

    return target_logout


def iscsi_discover(portal_ip):
    """
    Query from iscsi server for available targets

    :param portal_ip: Ip for iscsi server
    """
    cmd = "iscsiadm -m discovery -t sendtargets -p %s" % portal_ip
    output = process.run(cmd, ignore_status=True).stdout_text

    session = ""
    if "Invalid" in output:
        LOG.debug(output)
    else:
        session = output
    return session


class _IscsiComm(object):

    """
    Provide an interface to complete the similar initialization
    """

    def __init__(self, params, root_dir):
        """
        common __init__ function used to initialize iSCSI service

        :param params:      parameters dict for iSCSI
        :param root_dir:    path for image
        """
        self.target = params.get("target")
        self.export_flag = False
        self.luns = None
        self.iscsi_lun_attrs = params.get("iscsi_lun_attrs")
        self.restart_tgtd = 'yes' == params.get("restart_tgtd", "no")
        if params.get("portal_ip"):
            self.portal_ip = params.get("portal_ip")
        else:
            self.portal_ip = "127.0.0.1"
        if params.get("iscsi_thread_id"):
            self.id = params.get("iscsi_thread_id")
        else:
            self.id = data_factory.generate_random_string(4)
        self.initiator = params.get("initiator")

        # CHAP AUTHENTICATION
        self.chap_flag = False
        self.chap_user = params.get("chap_user")
        self.chap_passwd = params.get("chap_passwd")
        if self.chap_user and self.chap_passwd:
            self.chap_flag = True

        emulated_image = params.get("emulated_image")
        if not emulated_image:
            self.device = None
            return

        self.iscsi_backend = params.get("iscsi_backend")
        if not self.iscsi_backend:
            if emulated_image.startswith("/dev/"):
                self.iscsi_backend = "block"
            else:
                self.iscsi_backend = "fileio"

        if self.iscsi_backend == "fileio":
            self.initiator = None
            emulated_image = params.get("emulated_image")
            self.emulated_image = os.path.join(root_dir, emulated_image)
            self.device = "device.%s" % os.path.basename(self.emulated_image)
            self.emulated_id = ""
            self.emulated_size = params.get("image_size")
            self.unit = self.emulated_size[-1].upper()
            self.emulated_size = self.emulated_size[:-1]
            # maps K,M,G,T => (count, bs)
            emulated_size = {'K': (1, 1),
                             'M': (1, 1024),
                             'G': (1024, 1024),
                             'T': (1024, 1048576),
                             }
            if self.unit in emulated_size:
                block_size = emulated_size[self.unit][1]
                size = int(self.emulated_size) * emulated_size[self.unit][0]
                self.emulated_expect_size = block_size * size
                self.create_cmd = ("dd if=/dev/zero of=%s count=%s bs=%sK"
                                   % (self.emulated_image, size, block_size))
            else:
                raise exceptions.TestError("Image size provided is not in valid"
                                           " format, specify proper units [K|M|G|T]")
        else:
            self.emulated_image = emulated_image
            self.device = "device.%s" % os.path.basename(self.emulated_image)

    def logged_in(self):
        """
        Check if the session is login or not.
        """
        sessions = iscsi_get_sessions()
        login = False
        if self.target in list(map(lambda x: x[1], sessions)):
            login = True
        return login

    def portal_visible(self):
        """
        Check if the portal can be found or not.
        """
        return bool(re.findall("%s$" % self.target,
                               iscsi_discover(self.portal_ip), re.M))

    def set_initiatorName(self, id, name):
        """
        back up and set up the InitiatorName
        """
        if os.path.isfile("%s" % ISCSI_CONFIG_FILE):
            LOG.debug("Try to update iscsi initiatorname")
            # Don't override the backup file
            if not os.path.isfile("%s-%s" % (ISCSI_CONFIG_FILE, id)):
                cmd = "mv %s %s-%s" % (ISCSI_CONFIG_FILE, ISCSI_CONFIG_FILE, id)
                process.system(cmd)
            fd = open(ISCSI_CONFIG_FILE, 'w')
            fd.write("InitiatorName=%s" % name)
            fd.close()
            restart_iscsid()

    def login(self):
        """
        Login session for both real iscsi device and emulated iscsi.
        Include env check and setup.
        """
        login_flag = False
        if self.portal_visible():
            login_flag = True
        elif self.initiator:

            self.set_initiatorName(id=self.id, name=self.initiator)
            if self.portal_visible():
                login_flag = True
        elif self.emulated_image:
            self.export_target()
            # If both iSCSI server and iSCSI client are on localhost.
            # It's necessary to set up the InitiatorName.
            if "127.0.0.1" in self.portal_ip:
                self.set_initiatorName(id=self.id, name=self.target)
            if self.portal_visible():
                login_flag = True

        if login_flag:
            iscsi_login(self.target, self.portal_ip)

    def get_device_name(self):
        """
        Get device name from the target name.
        """
        cmd = "iscsiadm -m session -P 3"
        pattern = r"%s.*?disk\s(\w+)\s+\S+\srunning" % self.target
        device_name = []
        if self.logged_in():
            output = process.run(cmd).stdout_text
            targets = output.split('Target: ')[1:]
            for target in targets:
                if self.target in target:
                    device_name = re.findall(pattern, target, re.S)
            try:
                device_name = "/dev/%s" % device_name[0]
            except IndexError:
                LOG.error(
                    "Can not find target '%s' after login.", self.target)
        else:
            LOG.error("Session is not logged in yet.")
        return device_name

    def set_chap_auth_initiator(self):
        """
        Set CHAP authentication for initiator.
        """
        name_dict = {'node.session.auth.authmethod': 'CHAP'}
        name_dict['node.session.auth.username'] = self.chap_user
        name_dict['node.session.auth.password'] = self.chap_passwd
        for name in list(name_dict.keys()):
            cmd = "iscsiadm --mode node --targetname %s " % self.target
            cmd += "--op update --name %s --value %s" % (name, name_dict[name])
            try:
                process.system(cmd)
            except process.CmdError:
                LOG.error("Fail to set CHAP authentication for initiator")

    def logout(self):
        """
        Logout from target.
        """
        if self.logged_in():
            iscsi_logout(self.target)

    def cleanup(self, confirmed=False):
        """
        Clean up env after iscsi used.
        :param confirmed:    switch for cleanup all iscsi config
        """
        self.logout()
        iscsi_node_del(self.target)
        if os.path.isfile("%s-%s" % (ISCSI_CONFIG_FILE, self.id)):
            cmd = "mv %s-%s %s" % (ISCSI_CONFIG_FILE, self.id, ISCSI_CONFIG_FILE)
            process.system(cmd)
            restart_iscsid()
        if self.export_flag:
            self.delete_target()
        if confirmed:
            # clear the targetcli configuration
            if path.find_command("targetcli"):
                cmd = "targetcli clearconfig confirm=true"
                if process.system(cmd, shell=True) != 0:
                    LOG.error("targetcli configuration unable to clear")


class IscsiTGT(_IscsiComm):

    """
    iscsi support TGT backend used in RHEL6.
    """

    def __init__(self, params, root_dir):
        """
        initialize TGT backend for iSCSI

        :param params: parameters dict for TGT backend of iSCSI.
        """
        super(IscsiTGT, self).__init__(params, root_dir)

    def get_target_id(self):
        """
        Get target id from image name. Only works for emulated iscsi device
        """
        cmd = "tgtadm --lld iscsi --mode target --op show"
        target_info = process.run(cmd).stdout_text
        target_id = ""
        for line in re.split("\n", target_info):
            if re.findall("Target\s+(\d+)", line):
                target_id = re.findall("Target\s+(\d+)", line)[0]
            if re.findall("Backing store path:\s+(/+.+)", line):
                if self.emulated_image in line:
                    break
        else:
            target_id = ""

        return target_id

    def get_chap_accounts(self):
        """
        Get all CHAP authentication accounts
        """
        cmd = "tgtadm --lld iscsi --op show --mode account"
        all_accounts = process.run(cmd).stdout_text
        if all_accounts:
            all_accounts = list(map(str.strip, all_accounts.splitlines()[1:]))
        return all_accounts

    def add_chap_account(self):
        """
        Add CHAP authentication account
        """
        try:
            cmd = "tgtadm --lld iscsi --op new --mode account"
            cmd += " --user %s" % self.chap_user
            cmd += " --password %s" % self.chap_passwd
            process.system(cmd)
        except process.CmdError as err:
            LOG.error("Fail to add account: %s", err)

        # Check the new add account exist
        if self.chap_user not in self.get_chap_accounts():
            LOG.error("Can't find account %s" % self.chap_user)

    def delete_chap_account(self):
        """
        Delete the CHAP authentication account
        """
        if self.chap_user in self.get_chap_accounts():
            cmd = "tgtadm --lld iscsi --op delete --mode account"
            cmd += " --user %s" % self.chap_user
            process.system(cmd)

    def get_target_account_info(self):
        """
        Get the target account information
        """
        cmd = "tgtadm --lld iscsi --mode target --op show"
        target_info = process.run(cmd).stdout_text
        pattern = r"Target\s+\d:\s+%s" % self.target
        pattern += ".*Account information:\s(.*)ACL information"
        try:
            target_account = re.findall(pattern, target_info,
                                        re.S)[0].strip().splitlines()
        except IndexError:
            target_account = []
        return list(map(str.strip, target_account))

    def set_chap_auth_target(self):
        """
        Set CHAP authentication on a target, it will require authentication
        before an initiator is allowed to log in and access devices.
        """
        if self.chap_user not in self.get_chap_accounts():
            self.add_chap_account()
        if self.chap_user in self.get_target_account_info():
            LOG.debug("Target %s already has account %s", self.target,
                      self.chap_user)
        else:
            cmd = "tgtadm --lld iscsi --op bind --mode account"
            cmd += " --tid %s --user %s" % (self.emulated_id, self.chap_user)
            process.system(cmd)

    def export_target(self):
        """
        Export target in localhost for emulated iscsi
        """
        selinux_mode = None

        if not os.path.isfile(self.emulated_image):
            process.system(self.create_cmd)
        else:
            emulated_image_size = os.path.getsize(self.emulated_image) // 1024
            if emulated_image_size != self.emulated_expect_size:
                # No need to remove, rebuild is fine
                process.system(self.create_cmd)
        cmd = "tgtadm --lld iscsi --mode target --op show"
        try:
            output = process.run(cmd).stdout_text
        except process.CmdError:
            restart_tgtd()
            output = process.run(cmd).stdout_text
        if not re.findall("%s$" % self.target, output, re.M):
            LOG.debug("Need to export target in host")

            # Set selinux to permissive mode to make sure iscsi target
            # export successfully
            if utils_selinux.is_enforcing():
                selinux_mode = utils_selinux.get_status()
                utils_selinux.set_status("permissive")

            output = process.run(cmd).stdout_text
            used_id = re.findall("Target\s+(\d+)", output)
            emulated_id = 1
            while str(emulated_id) in used_id:
                emulated_id += 1
            self.emulated_id = str(emulated_id)
            cmd = "tgtadm --mode target --op new --tid %s" % self.emulated_id
            cmd += " --lld iscsi --targetname %s" % self.target
            process.system(cmd)
            cmd = "tgtadm --lld iscsi --op bind --mode target "
            cmd += "--tid %s -I ALL" % self.emulated_id
            process.system(cmd)
        else:
            target_strs = re.findall("Target\s+(\d+):\s+%s$" %
                                     self.target, output, re.M)
            self.emulated_id = target_strs[0].split(':')[0].split()[-1]

        cmd = "tgtadm --lld iscsi --mode target --op show"
        try:
            output = process.run(cmd).stdout_text
        except process.CmdError:   # In case service stopped
            restart_tgtd()
            output = process.run(cmd).stdout_text

        # Create a LUN with emulated image
        if re.findall(self.emulated_image, output, re.M):
            # Exist already
            LOG.debug("Exported image already exists.")
            self.export_flag = True
        else:
            tgt_str = re.search(r'.*(Target\s+\d+:\s+%s\s*.*)$' % self.target,
                                output, re.DOTALL)
            if tgt_str:
                luns = len(re.findall("\s+LUN:\s(\d+)",
                                      tgt_str.group(1), re.M))
            else:
                luns = len(re.findall("\s+LUN:\s(\d+)", output, re.M))
            cmd = "tgtadm --mode logicalunit --op new "
            cmd += "--tid %s --lld iscsi " % self.emulated_id
            cmd += "--lun %s " % luns
            cmd += "--backing-store %s" % self.emulated_image
            process.system(cmd)
            self.export_flag = True
            self.luns = luns

        # Restore selinux
        if selinux_mode is not None:
            utils_selinux.set_status(selinux_mode)

        if self.chap_flag:
            # Set CHAP authentication on the exported target
            self.set_chap_auth_target()
            # Set CHAP authentication for initiator to login target
            if self.portal_visible():
                self.set_chap_auth_initiator()

    def delete_target(self):
        """
        Delete target from host.
        """
        cmd = "tgtadm --lld iscsi --mode target --op show"
        output = process.run(cmd).stdout_text
        if re.findall("%s$" % self.target, output, re.M):
            if self.emulated_id:
                cmd = "tgtadm --lld iscsi --mode target --op delete "
                cmd += "--tid %s" % self.emulated_id
                process.system(cmd)
        if self.restart_tgtd:
            restart_tgtd()


class IscsiLIO(_IscsiComm):

    """
    iscsi support class for LIO backend used in RHEL7.
    """

    def __init__(self, params, root_dir):
        """
        initialize LIO backend for iSCSI

        :param params: parameters dict for LIO backend of iSCSI
        """
        super(IscsiLIO, self).__init__(params, root_dir)

    def get_target_id(self):
        """
        Get target id from image name.
        """
        cmd = "targetcli ls /iscsi 1"
        target_info = process.run(cmd).stdout_text
        target = None
        for line in re.split("\n", target_info)[1:]:
            if re.findall("o-\s\S+\s[\.]+\s\[TPGs:\s\d\]$", line):
                # eg: iqn.2015-05.com.example:iscsi.disk
                try:
                    target = re.findall("iqn[\.]\S+:\S+", line)[0]
                except IndexError:
                    LOG.info("No found target in %s", line)
                    continue
            else:
                continue

            cmd = "targetcli ls /iscsi/%s/tpg1/luns" % target
            luns_info = process.run(cmd).stdout_text
            for lun_line in re.split("\n", luns_info):
                if re.findall("o-\slun\d+", lun_line):
                    if self.emulated_image in lun_line:
                        break
                    else:
                        target = None
        return target

    def set_chap_acls_target(self):
        """
        set CHAP(acls) authentication on a target.
        it will require authentication
        before an initiator is allowed to log in and access devices.

        notice:
            Individual ACL entries override common TPG Authentication,
            which can be set by set_chap_auth_target().
        """
        # Enable ACL nodes
        acls_cmd = "targetcli /iscsi/%s/tpg1/ " % self.target
        attr_cmd = "set attribute generate_node_acls=0"
        process.system(acls_cmd + attr_cmd)

        # Create user and allow access
        acls_cmd = ("targetcli /iscsi/%s/tpg1/acls/ create %s:client"
                    % (self.target, self.target.split(":")[0]))
        output = process.run(acls_cmd).stdout_text
        if "Created Node ACL" not in output:
            raise exceptions.TestFail("Failed to create ACL. (%s)" % output)

        comm_cmd = ("targetcli /iscsi/%s/tpg1/acls/%s:client/"
                    % (self.target, self.target.split(":")[0]))
        # Set userid
        userid_cmd = "%s set auth userid=%s" % (comm_cmd, self.chap_user)
        output = process.run(userid_cmd).stdout_text
        if self.chap_user not in output:
            raise exceptions.TestFail("Failed to set user. (%s)" % output)

        # Set password
        passwd_cmd = "%s set auth password=%s" % (comm_cmd, self.chap_passwd)
        output = process.run(passwd_cmd).stdout_text
        if self.chap_passwd not in output:
            raise exceptions.TestFail("Failed to set password. (%s)" % output)

        # Save configuration
        process.system("targetcli / saveconfig")

    def set_chap_auth_target(self):
        """
        set up authentication information for every single initiator,
        which provides the capability to define common login information
        for all Endpoints in a TPG
        """
        auth_cmd = "targetcli /iscsi/%s/tpg1/ " % self.target
        attr_cmd = ("set attribute %s %s %s" %
                    ("demo_mode_write_protect=0",
                     "generate_node_acls=1",
                     "cache_dynamic_acls=1"))
        process.system(auth_cmd + attr_cmd)

        # Set userid
        userid_cmd = "%s set auth userid=%s" % (auth_cmd, self.chap_user)
        output = process.run(userid_cmd).stdout_text
        if self.chap_user not in output:
            raise exceptions.TestFail("Failed to set user. (%s)" % output)

        # Set password
        passwd_cmd = "%s set auth password=%s" % (auth_cmd, self.chap_passwd)
        output = process.run(passwd_cmd).stdout_text
        if self.chap_passwd not in output:
            raise exceptions.TestFail("Failed to set password. (%s)" % output)

        # Save configuration
        process.system("targetcli / saveconfig")

    def export_target(self):
        """
        Export target in localhost for emulated iscsi
        """
        selinux_mode = None
        if self.iscsi_backend == "fileio":
            # create image disk
            if not os.path.isfile(self.emulated_image):
                process.system(self.create_cmd)
            else:
                emulated_image_size = os.path.getsize(
                    self.emulated_image) // 1024
                if emulated_image_size != self.emulated_expect_size:
                    # No need to remove, rebuild is fine
                    process.system(self.create_cmd)

        # confirm if the target exists and create iSCSI target
        cmd = "targetcli ls /iscsi 1"
        output = process.run(cmd).stdout_text
        if not re.findall("%s$" % self.target, output, re.M):
            LOG.debug("Need to export target in host")

            # Set selinux to permissive mode to make sure
            # iscsi target export successfully
            if utils_selinux.is_enforcing():
                selinux_mode = utils_selinux.get_status()
                utils_selinux.set_status("permissive")

            # In fact, We've got two options here
            #
            # 1) Create a block backstore that usually provides the best
            #    performance. We can use a block device like /dev/sdb or
            #    a logical volume previously created,
            #     (lvcreate -name lv_iscsi -size 1G vg)
            # 2) Create a fileio backstore,
            #    which enables the local file system cache.

            # Create a backstore
            device_cmd = ("targetcli /backstores/%s/ create %s %s" %
                          (self.iscsi_backend, self.device,
                           self.emulated_image))
            output = process.run(device_cmd).stdout_text
            if "Created %s" % self.iscsi_backend not in output:
                raise exceptions.TestFail("Failed to create %s %s. (%s)" %
                                          (self.iscsi_backend, self.device,
                                           output))

            # Set attribute
            if self.iscsi_lun_attrs:
                attr_cmd = "targetcli /backstores/%s/%s set attribute %s" % (
                    self.iscsi_backend, self.device, self.iscsi_lun_attrs)
                process.system(attr_cmd)

            # Create an IQN with a target named target_name
            target_cmd = "targetcli /iscsi/ create %s" % self.target
            output = process.run(target_cmd).stdout_text
            if "Created target" not in output:
                raise exceptions.TestFail("Failed to create target %s. (%s)" %
                                          (self.target, output))

            check_portal = "targetcli /iscsi/%s/tpg1/portals ls" % self.target
            portal_info = process.run(check_portal).stdout_text
            if "0.0.0.0:3260" not in portal_info:
                # Create portal
                # 0.0.0.0 means binding to INADDR_ANY
                # and using default IP port 3260
                portal_cmd = ("targetcli /iscsi/%s/tpg1/portals/ create %s"
                              % (self.target, "0.0.0.0"))
                output = process.run(portal_cmd).stdout_text
                if "Created network portal" not in output:
                    raise exceptions.TestFail("Failed to create portal. (%s)" %
                                              output)
            if ("ipv6" == utils_net.IPAddress(self.portal_ip).version and
                    self.portal_ip not in portal_info):
                # Ipv6 portal address can't be created by default,
                # create ipv6 portal if needed.
                portal_cmd = ("targetcli /iscsi/%s/tpg1/portals/ create %s"
                              % (self.target, self.portal_ip))
                output = process.run(portal_cmd).stdout_text
                if "Created network portal" not in output:
                    raise exceptions.TestFail("Failed to create portal. (%s)" %
                                              output)
            # Create lun
            lun_cmd = "targetcli /iscsi/%s/tpg1/luns/ " % self.target
            dev_cmd = "create /backstores/%s/%s" % (
                self.iscsi_backend, self.device)
            output = process.run(lun_cmd + dev_cmd).stdout_text
            luns = re.findall(r"Created LUN (\d+).", output)
            if not luns:
                raise exceptions.TestFail("Failed to create lun. (%s)" %
                                          output)
            self.luns = luns[0]

            # Set firewall if it's enabled
            output = process.run("firewall-cmd --state",
                                 ignore_status=True).stdout_text
            if re.findall("^running", output, re.M):
                # firewall is running
                process.system("firewall-cmd --permanent --add-port=3260/tcp")
                process.system("firewall-cmd --reload")

            # Restore selinux
            if selinux_mode is not None:
                utils_selinux.set_status(selinux_mode)

            self.export_flag = True
        else:
            LOG.info("Target %s has already existed!" % self.target)

        if self.chap_flag:
            # Set CHAP authentication on the exported target
            self.set_chap_auth_target()
            # Set CHAP authentication for initiator to login target
            if self.portal_visible():
                self.set_chap_auth_initiator()
        else:
            # To enable that so-called "demo mode" TPG operation,
            # disable all authentication for the corresponding Endpoint.
            # which means grant access to all initiators,
            # so that they can access all LUNs in the TPG
            # without further authentication.
            auth_cmd = "targetcli /iscsi/%s/tpg1/ " % self.target
            attr_cmd = ("set attribute %s %s %s %s" %
                        ("authentication=0",
                         "demo_mode_write_protect=0",
                         "generate_node_acls=1",
                         "cache_dynamic_acls=1"))
            output = process.run(auth_cmd + attr_cmd).stdout_text
            LOG.info("Define access rights: %s" % output)
            # Discovery the target
            self.portal_visible()

        # Save configuration
        process.system("targetcli / saveconfig")

        # Restart iSCSI service
        restart_iscsid()

    def delete_target(self):
        """
        Delete target from host.
        """
        # Delete block
        if self.device is not None:
            cmd = "targetcli /backstores/%s ls" % self.iscsi_backend
            output = process.run(cmd).stdout_text
            if re.findall("%s" % self.device, output, re.M):
                dev_del = ("targetcli /backstores/%s/ delete %s"
                           % (self.iscsi_backend, self.device))
                process.system(dev_del)

        # Delete IQN
        cmd = "targetcli ls /iscsi 1"
        output = process.run(cmd).stdout_text
        if re.findall("%s" % self.target, output, re.M):
            del_cmd = "targetcli /iscsi delete %s" % self.target
            process.system(del_cmd)

        # Save deleted configuration to avoid restoring
        cmd = "targetcli / saveconfig"
        process.system(cmd)


class Iscsi(object):

    """
    Basic iSCSI support class,
    which will handle the emulated iscsi export and
    access to both real iscsi and emulated iscsi device.

    The class support different kinds of iSCSI backend (TGT and LIO),
    and return ISCSI instance.
    """
    @staticmethod
    def create_iSCSI(params, root_dir=data_dir.get_tmp_dir()):
        iscsi_instance = None
        ubuntu = distro.detect().name == 'Ubuntu'
        # check and install iscsi initiator packages
        if ubuntu:
            iscsi_package = ["open-iscsi"]
        else:
            iscsi_package = ["iscsi-initiator-utils"]

        if not utils_package.package_install(iscsi_package):
            raise exceptions.TestError("Failed to install iscsi initiator"
                                       " packages")
        # Install linux iscsi target software targetcli
        iscsi_package = ["targetcli"]
        if not utils_package.package_install(iscsi_package):
            LOG.error("Failed to install targetcli trying with scsi-"
                      "target-utils or tgt package")
            # try with scsi target utils if targetcli is not available
            if ubuntu:
                iscsi_package = ["tgt"]
            else:
                iscsi_package = ["scsi-target-utils"]
            if not utils_package.package_install(iscsi_package):
                raise exceptions.TestError("Failed to install iscsi target and"
                                           " initiator packages")
            iscsi_instance = IscsiTGT(params, root_dir)
        else:
            iscsi_instance = IscsiLIO(params, root_dir)
        return iscsi_instance
