"""
Basic nfs support for Linux host. It can support the remote
nfs mount and the local nfs set up and mount.
"""
import re
import aexpect
import logging

from avocado.utils import path
from avocado.utils import process
from avocado.utils import distro
from avocado.utils.astring import to_text
from avocado.core import exceptions

from virttest import utils_misc
from virttest import test_setup
from virttest.utils_iptables import Iptables
from virttest.utils_conn import SSHConnection
from virttest.staging import service


def nfs_exported(session=None):
    """
    Get the list for nfs file system already exported

    :param session: ShellSessionObject of remote/guest

    :return: a list of nfs that is already exported in system
    :rtype: a lit of nfs file system exported
    """
    func = process.system_output
    if session:
        func = session.cmd_output
    exportfs = to_text(func("exportfs -v"))
    if not exportfs:
        return {}

    nfs_exported_dict = {}
    for fs_info in re.findall("[/\w+]+.*?\(.*?\)", exportfs, re.S):
        fs_info = fs_info.strip().split()
        if len(fs_info) == 2:
            nfs_src = fs_info[0]
            access_ip = re.findall(r"(.*)\(", fs_info[1])[0]
            if "world" in access_ip:
                access_ip = "*"
            nfs_tag = "%s_%s" % (nfs_src, access_ip)
            permission = re.findall(r"\((.*)\)", fs_info[1])[0]
            nfs_exported_dict[nfs_tag] = permission

    return nfs_exported_dict


class Exportfs(object):

    """
    Add or remove one entry to exported nfs file system.
    """

    def __init__(self, path, client="*", options="", ori_exported=None, session=None):
        if ori_exported is None:
            ori_exported = []
        self.path = path
        self.client = client
        self.options = options.split(",")
        self.ori_exported = ori_exported
        self.entry_tag = "%s_%s" % (self.path, self.client)
        self.already_exported = False
        self.ori_options = ""
        self.session = session
        self.func = process.getoutput
        if self.session:
            self.func = self.session.cmd_output

    def is_exported(self):
        """
        Check if the directory is already exported.

        :return: If the entry is exported
        :rtype: Boolean
        """
        ori_exported = self.ori_exported or nfs_exported(session=self.session)
        if self.entry_tag in list(ori_exported.keys()):
            return True
        return False

    def need_reexport(self):
        """
        Check if the entry is already exported but the options are not
        the same as we required.

        :return: Need re export the entry or not
        :rtype: Boolean
        """
        ori_exported = self.ori_exported or nfs_exported(session=self.session)
        if self.is_exported():
            exported_options = ori_exported[self.entry_tag]
            options = [_ for _ in self.options if _ not in exported_options]
            if options:
                self.ori_options = exported_options
                return True
        return False

    def unexport(self):
        """
        Unexport an entry.
        """
        if self.is_exported():
            unexport_cmd = "exportfs -u %s:%s" % (self.client, self.path)
            self.func(unexport_cmd)
        else:
            logging.warn("Target %s %s is not exported yet."
                         "Can not unexport it." % (self.client, self.path))

    def reset_export(self):
        """
        Reset the exportfs to the original status before we export the
        specific entry.
        """
        self.unexport()
        if self.ori_options:
            tmp_options = self.options
            self.options = self.ori_options.split(",")
            self.export()
            self.options = tmp_options

    def export(self):
        """
        Export one directory if it is not in exported list.

        :return: Export nfs file system succeed or not
        """
        if self.is_exported():
            if self.need_reexport():
                self.unexport()
            else:
                self.already_exported = True
                logging.warn("Already exported target."
                             " Don't need export it again")
                return True
        export_cmd = "exportfs"
        if self.options:
            export_cmd += " -o %s" % ",".join(self.options)
        export_cmd += " %s:%s" % (self.client, self.path)
        try:
            self.func(export_cmd)
        except (process.CmdError, aexpect.ShellTimeoutError) as export_failed_err:
            logging.error("Can not export target: %s" % export_failed_err)
            return False
        return True


class Nfs(object):

    """
    Nfs class for handle nfs mount and umount. If a local nfs service is
    required, it will configure a local nfs server accroding the params.
    """

    def __init__(self, params):
        self.mount_dir = params.get("nfs_mount_dir")
        self.mount_options = params.get("nfs_mount_options")
        self.mount_src = params.get("nfs_mount_src")
        self.nfs_setup = False
        path.find_command("mount")
        self.rm_mount_dir = False
        self.rm_export_dir = False
        self.unexportfs_in_clean = False
        distro_details = distro.detect().name
        self.session = None
        self.setup_nfs_ip = params.get("nfs_server_ip", "127.0.0.1")
        self.export_dir = (params.get("export_dir") or
                           self.mount_src.split(":")[-1])
        self.export_ip = params.get("export_ip", "*")
        self.export_options = params.get("export_options", "").strip()

        if params.get("setup_remote_nfs") == "yes":
            self.nfs_setup = True
            self.setup_nfs_ip = params["nfs_server_ip"]
            nfs_server_params = {'server_ip': self.setup_nfs_ip,
                                 'server_pwd': params["nfs_server_pwd"],
                                 'server_user': params.get("nfs_server_user",
                                                           "root")}
            self.session = test_setup.remote_session(nfs_server_params)
            distro_details = utils_misc.get_distro(self.session)
            if self.session.cmd_status("exportfs -h") != 0:
                logging.error("exportfs cmd not available in remote host")

        elif params.get("setup_local_nfs") == "yes":
            self.nfs_setup = True
            self.setup_nfs_ip = "127.0.0.1"
            path.find_command("service")
            path.find_command("exportfs")

        if(params.get("setup_remote_nfs") == "yes" or
           params.get("setup_local_nfs") == "yes"):
            if 'Ubuntu' in distro_details or 'rhel' in distro_details:
                self.nfs_service = service.Service("nfs-server",
                                                   session=self.session)
            else:
                self.nfs_service = service.Service("nfs", session=self.session)

            self.rpcbind_service = service.Service("rpcbind", session=self.session)
            self.exportfs = Exportfs(self.export_dir, self.export_ip,
                                     self.export_options, session=self.session)
        self.mount_src = "%s:%s" % (self.setup_nfs_ip, self.export_dir)

    def is_mounted(self):
        """
        Check the NFS is mounted or not.

        :return: If the src is mounted as expect
        :rtype: Boolean
        """
        return utils_misc.is_mounted(self.mount_src, self.mount_dir, "nfs")

    def mount(self):
        """
        Mount source into given mount point.
        """
        return utils_misc.mount(self.mount_src, self.mount_dir, "nfs",
                                perm=self.mount_options)

    def umount(self):
        """
        Umount the given mount point.
        """
        return utils_misc.umount(self.mount_src, self.mount_dir, "nfs")

    def setup(self):
        """
        Setup NFS in host.

        Mount NFS as configured. If a local nfs is requested, setup the NFS
        service and exportfs too.
        """
        if self.nfs_setup:
            if not self.nfs_service.status():
                logging.debug("Restart NFS service.")
                self.rpcbind_service.restart()
                self.nfs_service.restart()

            if not utils_misc.check_isdir(self.export_dir, session=self.session):
                utils_misc.make_dirs(self.export_dir, session=self.session)
                self.rm_export_dir = True
            self.exportfs.export()
            self.unexportfs_in_clean = not self.exportfs.already_exported

        logging.debug("Mount %s to %s" % (self.mount_src, self.mount_dir))
        if(utils_misc.check_exists(self.mount_dir, session=self.session)
           and not utils_misc.check_isdir(self.mount_dir, session=self.session)):
            raise OSError(
                "Mount point %s is not a directory, check your setup." %
                self.mount_dir)

        if not utils_misc.check_isdir(self.mount_dir, session=self.session):
            utils_misc.make_dirs(self.mount_dir, session=self.session)
            self.rm_mount_dir = True
        self.mount()

    def cleanup(self):
        """
        Clean up the host env.

        Umount NFS from the mount point. If there has some change for exported
        file system in host when setup, also clean up that.
        """
        self.umount()
        if self.nfs_setup and self.unexportfs_in_clean:
            self.exportfs.reset_export()
            if self.rm_export_dir and utils_misc.check_isdir(self.export_dir,
                                                             session=self.session):
                utils_misc.safe_rmdir(self.export_dir)
        if self.rm_mount_dir and utils_misc.check_isdir(self.mount_dir,
                                                        session=self.session):
            utils_misc.safe_rmdir(self.mount_dir, session=self.session)


class NFSClient(object):

    """
    NFSClient class for handle nfs remotely mount and umount.
    """

    def __init__(self, params):
        self.nfs_client_ip = params.get("nfs_client_ip")
        # To Avoid host key verification failure
        ret = process.run("ssh-keygen -R %s" % self.nfs_client_ip,
                          ignore_status=True)
        stderr = ret.stderr_text
        if ret.exit_status and "No such file or directory" not in stderr:
            raise exceptions.TestFail("Failed to update host key: %s" %
                                      stderr)
        # Setup SSH connection
        self.ssh_obj = SSHConnection(params)
        ssh_timeout = int(params.get("ssh_timeout", 10))
        self.ssh_obj.conn_setup(timeout=ssh_timeout)

        self.params = params
        self.mkdir_mount_remote = False
        self.mount_dir = params.get("nfs_mount_dir")
        self.mount_options = params.get("nfs_mount_options")
        self.mount_src = params.get("nfs_mount_src")
        self.nfs_server_ip = params.get("nfs_server_ip")
        self.ssh_user = params.get("ssh_username", "root")
        self.remote_nfs_mount = params.get("remote_nfs_mount", "yes")
        self.ssh_hostkey_check = params.get("ssh_hostkey_check", "no") == "yes"
        self.ssh_cmd = "ssh %s@%s " % (self.ssh_user, self.nfs_client_ip)
        if not self.ssh_hostkey_check:
            self.ssh_cmd += "-o StrictHostKeyChecking=no "

    def is_mounted(self):
        """
        Check the NFS is mounted or not.

        :return: If the src is mounted as expect
        :rtype: Boolean
        """
        find_mountpoint_cmd = "mount | grep -E '.*%s.*%s.*'" % (self.mount_src,
                                                                self.mount_dir)
        cmd = self.ssh_cmd + "'%s'" % find_mountpoint_cmd
        logging.debug("The command: %s", cmd)
        status, output = process.getstatusoutput(cmd)
        if status:
            logging.debug("The command result: <%s:%s>", status, output)
            return False
        return True

    def setup(self):
        """
        Setup NFS client.
        """
        # Mount sharing directory to local host
        # it has been covered by class Nfs

        # Mount sharing directory to remote host
        if self.remote_nfs_mount == "yes":
            # stale file mounted causes test to fail instead
            # unmount it and perform the setup
            if self.is_mounted():
                self.umount()
            self.setup_remote()

    def umount(self):
        """
        Unmount the mount directory in remote host
        """
        logging.debug("Umount %s from %s" %
                      (self.mount_dir, self.nfs_client_ip))
        umount_cmd = self.ssh_cmd + "'umount -l %s'" % self.mount_dir
        try:
            process.system(umount_cmd, verbose=True)
        except process.CmdError:
            raise exceptions.TestFail("Failed to run: %s" % umount_cmd)

    def cleanup(self, ssh_auto_recover=False):
        """
        Cleanup NFS client.
        """
        self.umount()
        if self.mkdir_mount_remote:
            rmdir_cmd = self.ssh_cmd + "'rm -rf %s'" % self.mount_dir
            try:
                process.system(rmdir_cmd, verbose=True)
            except process.CmdError:
                raise exceptions.TestFail("Failed to run: %s" % rmdir_cmd)

        if self.is_mounted():
            raise exceptions.TestFail("Failed to umount %s" % self.mount_dir)

        # Recover SSH connection
        if ssh_auto_recover:
            self.ssh_obj.auto_recover = ssh_auto_recover
            del self.ssh_obj

    def firewall_to_permit_nfs(self):
        """
        Method to configure firewall to permit NFS to be mounted
        from remote host
        """
        # Check firewall in host permit nfs service to mount from remote server
        try:
            firewalld = service.Factory.create_service("firewalld")
            if not firewalld.status():
                firewalld.start()
            firewall_cmd = "firewall-cmd --list-all | grep services:"
            try:
                ret = process.run(firewall_cmd, shell=True)
                if not ret.exit_status:
                    firewall_services = ret.stdout_text.split(':')[1].strip().split(' ')
                    if 'nfs' not in firewall_services:
                        service_cmd = "firewall-cmd --permanent --zone=public "
                        service_cmd += "--add-service=nfs"
                        ret = process.run(service_cmd, shell=True)
                        if ret.exit_status:
                            logging.error("nfs service not added in firewall: "
                                          "%s", ret.stdout_text)
                        else:
                            logging.debug("nfs service added to firewall "
                                          "sucessfully")
                            firewalld.restart()
                    else:
                        logging.debug("nfs service already permitted by firewall")
            except process.CmdError:
                # For RHEL 6 based system firewall-cmd is not available
                logging.debug("Using iptables to permit NFS service")
                nfs_ports = []
                rule_list = []
                nfsd = service.Factory.create_service("nfs")
                rpcd = service.Factory.create_service("rpcbind")
                iptables = service.Factory.create_service("iptables")
                nfs_sysconfig = self.params.get("nfs_sysconfig_path",
                                                "/etc/sysconfig/nfs")
                tcp_port = self.params.get("nfs_tcp_port", "32803")
                udp_port = self.params.get("nfs_udp_port", "32769")
                mountd_port = self.params.get("nfs_mountd_port", "892")
                subnet_mask = self.params.get("priv_subnet", "192.168.2.0/24")
                nfs_ports.append("LOCKD_TCPPORT=%s" % tcp_port)
                nfs_ports.append("LOCKD_UDPPORT=%s" % udp_port)
                nfs_ports.append("MOUNTD_PORT=%s" % mountd_port)
                cmd_output = process.run("cat %s" % nfs_sysconfig,
                                         shell=True).stdout_text
                exist_ports = cmd_output.strip().split('\n')
                # check if the ports are already configured, if not then add it
                for each_port in nfs_ports:
                    if each_port not in exist_ports:
                        process.run("echo '%s' >> %s" %
                                    (each_port, nfs_sysconfig), shell=True)
                rpcd.restart()
                nfsd.restart()
                rule_temp = "INPUT -m state --state NEW -p %s -m multiport "
                rule_temp += "--dport 111,892,2049,%s -s %s -j ACCEPT"
                rule = rule_temp % ("tcp", tcp_port, subnet_mask)
                rule_list.append(rule)
                rule = rule_temp % ("udp", udp_port, subnet_mask)
                rule_list.append(rule)
                Iptables.setup_or_cleanup_iptables_rules(rule_list)
                iptables.restart()
        except Exception as info:
            logging.error("Firewall setting to add nfs service "
                          "failed: %s", info)

    def setup_remote(self):
        """
        Mount sharing directory to remote host.
        """
        check_mount_dir_cmd = self.ssh_cmd + "'ls -d %s'" % self.mount_dir
        logging.debug("To check if the %s exists", self.mount_dir)
        output = process.getoutput(check_mount_dir_cmd)
        if re.findall("No such file or directory", output, re.M):
            mkdir_cmd = self.ssh_cmd + "'mkdir -p %s'" % self.mount_dir
            logging.debug("Prepare to create %s", self.mount_dir)
            s, o = process.getstatusoutput(mkdir_cmd)
            if s != 0:
                raise exceptions.TestFail("Failed to run %s: %s" %
                                          (mkdir_cmd, o))
            self.mkdir_mount_remote = True

        if self.params.get("firewall_to_permit_nfs", "yes") == "yes":
            if distro.detect().name != "Ubuntu":
                self.firewall_to_permit_nfs()

        self.mount_src = "%s:%s" % (self.nfs_server_ip, self.mount_src)
        logging.debug("Mount %s to %s" % (self.mount_src, self.mount_dir))
        mount_cmd = "mount -t nfs %s %s" % (self.mount_src, self.mount_dir)
        if self.mount_options:
            mount_cmd += " -o %s" % self.mount_options
        try:
            cmd = "%s '%s'" % (self.ssh_cmd, mount_cmd)
            process.system(cmd, verbose=True)
        except process.CmdError:
            raise exceptions.TestFail("Failed to run: %s" % cmd)

        # Check if the sharing directory is mounted
        if not self.is_mounted():
            raise exceptions.TestFail("Failed to mount from %s to %s" %
                                      self.mount_src, self.mount_dir)
