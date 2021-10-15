import os
import logging
import re

import aexpect
from aexpect import remote

from avocado.utils import download
from avocado.utils import aurl
from avocado.utils import wait

from six.moves import xrange

from . import data_dir
from . import remote as remote_old

LOG = logging.getLogger('avocado.' + __name__)


class NetperfError(Exception):
    pass


class NetperfPackageError(NetperfError):

    def __init__(self, error_info):
        NetperfError.__init__(self)
        self.error_info = error_info

    def __str__(self):
        e_msg = "Packeage Error: %s" % self.error_info
        return e_msg


class NetserverError(NetperfError):

    def __init__(self, error_info):
        NetperfError.__init__(self)
        self.error_info = error_info

    def __str__(self):
        e_msg = "%s" % self.error_info
        return e_msg


class NetperfTestError(NetperfError):

    def __init__(self, error_info):
        NetperfError.__init__(self)
        self.error_info = error_info

    def __str__(self):
        e_msg = "Netperf test error: %s" % self.error_info
        return e_msg


class NetperfPackage(remote_old.Remote_Package):

    def __init__(self, address, netperf_path, md5sum="", netperf_source="",
                 client="ssh", port="22", username="root", password="123456",
                 prompt="^root@.*[\#\$]\s*$|", linesep="\n", status_test_command="echo $?"):
        """
        Class NetperfPackage just represent the netperf package
        Init NetperfPackage class.

        :param address: Remote host or guest address
        :param netperf_path: Installed netperf path
        :param me5sum: Local netperf package me5sum
        :param netperf_source: source netperf (path or link) path
        :param client: The client to use ('ssh', 'telnet' or 'nc')
        :param port: Port to connect to
        :param username: Username (if required)
        :param password: Password (if required)
        """
        super(NetperfPackage, self).__init__(address, client, username,
                                             password, port, netperf_path)

        self.netperf_source = netperf_source
        self.pack_suffix = ""
        self.netperf_dir = None
        self.build_tool = False
        self.md5sum = md5sum
        self.netperf_base_dir = self.remote_path
        self.netperf_file = os.path.basename(self.netperf_source)

        if client == "ssh":
            if self.netperf_source.endswith("tar.bz2"):
                self.pack_suffix = ".tar.bz2"
                self.decomp_cmd = "tar jxf"
            elif self.netperf_source.endswith("tar.gz"):
                self.pack_suffix = ".tar.gz"
                self.decomp_cmd = "tar zxf"
            self.netperf_dir = os.path.join(self.remote_path,
                                            self.netperf_file.rstrip(self.pack_suffix))

        if self.pack_suffix:
            self.netserver_path = os.path.join(self.netperf_dir,
                                               "src/netserver")
            self.netperf_path = os.path.join(self.netperf_dir,
                                             "src/netperf")
        else:
            self.netserver_path = os.path.join(self.netperf_base_dir,
                                               self.netperf_file)
            self.netperf_path = os.path.join(self.netperf_base_dir,
                                             self.netperf_file)

        LOG.debug("Create remote session")
        self.session = remote.remote_login(self.client, self.address,
                                           self.port, self.username,
                                           self.password, prompt,
                                           linesep, timeout=360,
                                           status_test_command=status_test_command)

    def env_cleanup(self, clean_all=True):
        clean_cmd = ""
        if self.netperf_dir:
            clean_cmd = "rm -rf %s" % self.netperf_dir
        if clean_all:
            clean_cmd += " rm -rf %s" % os.path.join(self.remote_path,
                                                     self.netperf_file)
        self.session.cmd(clean_cmd, ignore_all_errors=True)

    def pack_compile(self, compile_option=""):
        pre_setup_cmd = "cd %s " % self.netperf_base_dir
        pre_setup_cmd += " && %s %s" % (self.decomp_cmd, self.netperf_file)
        pre_setup_cmd += " && cd %s " % self.netperf_dir
        # Create dict to make other OS architectures easy to extend
        build_type = {"aarch64": "aarch64-unknown-linux-gnu"}
        build_arch = self.session.cmd_output("arch", timeout=60).strip()
        np_build = build_type.get(build_arch, build_arch).strip()
        setup_cmd = "./autogen.sh > /dev/null 2>&1 &&" \
                    " ./configure --build=%s %s > /dev/null 2>&1" % (np_build,
                                                                     compile_option)
        setup_cmd += " && make > /dev/null 2>&1"
        self.env_cleanup(clean_all=False)
        cmd = "%s && %s " % (pre_setup_cmd, setup_cmd)
        try:
            self.session.cmd(cmd, timeout=1200)
        except aexpect.ShellError as e:
            raise NetperfPackageError("Compile failed: %s" % e)

    def pull_file(self, netperf_source=None):
        """
        Copy file from remote to local.
        """

        if aurl.is_url(netperf_source):
            LOG.debug("Download URL file to local path")
            tmp_dir = data_dir.get_download_dir()
            dst = os.path.join(tmp_dir, os.path.basename(netperf_source))
            self.netperf_source = download.get_file(src=netperf_source,
                                                    dst=dst,
                                                    hash_expected=self.md5sum)
        else:
            self.netperf_source = netperf_source
        return self.netperf_source

    def install(self, install, compile_option):
        cmd = "which netperf"
        try:
            status, netperf = self.session.cmd_status_output(cmd)
        except aexpect.ShellError:
            status = 1
        if not status:
            self.netperf_path = netperf.rstrip()
            cmd = "which netserver"
            self.netserver_path = self.session.cmd_output(cmd).rstrip()
            install = False
        if install:
            self.build_tool = True
            self.pull_file(self.netperf_source)
            self.push_file(self.netperf_source)
            if self.pack_suffix:
                LOG.debug("Compiling netserver from source")
                self.pack_compile(compile_option)

        msg = "Using local netperf: %s and %s" % (self.netperf_path,
                                                  self.netserver_path)
        LOG.debug(msg)
        return (self.netserver_path, self.netperf_path)


class Netperf(object):

    def __init__(self, address, netperf_path, md5sum="", netperf_source="",
                 client="ssh", port="22", username="root", password="redhat",
                 prompt="^root@.*[\#\$]\s*$|", linesep="\n", status_test_command="echo $?",
                 compile_option="--enable-demo=yes", install=True):
        """
        Init Netperf class.

        :param address: Remote host or guest address
        :param netperf_path: Remote netperf path
        :param me5sum: Local netperf package me5sum
        :param netperf_source: netperf source file (path or link) which will
                               transfer to remote
        :param client: The client to use ('ssh', 'telnet' or 'nc')
        :param port: Port to connect to
        :param username: Username (if required)
        :param password: Password (if required)
        :param compile_option: Compile option for netperf
        :param install: Whether need install netperf or not.
        """
        self.client = client

        self.package = NetperfPackage(address, netperf_path, md5sum,
                                      netperf_source, client, port, username,
                                      password, prompt, linesep, status_test_command)
        self.netserver_path, self.netperf_path = self.package.install(install,
                                                                      compile_option)
        LOG.debug("Create remote session")
        self.session = remote.remote_login(client, address, port, username,
                                           password, prompt,
                                           linesep, timeout=360,
                                           status_test_command=status_test_command)

    def is_target_running(self, target):
        list_cmd = "ps -C %s" % target
        if self.client == "nc":
            list_cmd = "wmic process where name='%s' list" % target
        try:
            output = self.session.cmd_output_safe(list_cmd, timeout=120)
            check_reg = re.compile(r"%s" % target, re.I | re.M)
            return bool(check_reg.findall(output))
        except Exception as err:
            LOG.debug("Check process error: %s" % str(err))
        return False

    def stop(self, target):
        if self.client == "nc":
            stop_cmd = "taskkill /F /IM %s*" % target
        else:
            stop_cmd = "killall %s" % target
        if self.is_target_running(target):
            self.session.cmd(stop_cmd, ignore_all_errors=True)
        if self.is_target_running(target):
            raise NetserverError("Cannot stop %s" % target)
        LOG.info("Stop %s successfully" % target)

    def cleanup(self, clean_all=True):
        """
        Cleanup the netperf packages.

        :param clean_all: True to delete both netperf binary and source tarball
                          and False to delete only binary.
        """
        self.package.env_cleanup(clean_all=clean_all)


class NetperfServer(Netperf):

    def __init__(self, address, netperf_path, md5sum="", netperf_source="",
                 client="ssh", port="22", username="root", password="redhat",
                 prompt="^root@.*[\#\$]\s*$|", linesep="\n", status_test_command="echo $?",
                 compile_option="--enable-demo=yes", install=True):
        """
        Init NetperfServer class.

        :param address: Remote host or guest address
        :param netperf_path: Remote netperf path
        :param me5sum: Local netperf package me5sum
        :param netperf_source: Local netperf (path or link) with will transfer to
                           remote
        :param client: The client to use ('ssh', 'telnet' or 'nc')
        :param port: Port to connect to
        :param username: Username (if required)
        :param password: Password (if required)
        :param compile_option: Compile option for netperf
        :param install: Whether need install netperf or not.
        """
        super(NetperfServer, self).__init__(address, netperf_path, md5sum,
                                            netperf_source, client, port, username,
                                            password, prompt, linesep, status_test_command,
                                            compile_option, install)

    def start(self, restart=False):
        """
        Start/Restart netserver

        :param restart: if restart=True, will restart the netserver
        """

        LOG.info("Start netserver ...")
        server_cmd = ""
        if self.client == "nc":
            server_cmd += "start /b %s > null" % self.netserver_path
        else:
            server_cmd = "%s > /dev/null" % self.netserver_path

        if restart:
            self.stop()
        if not self.is_server_running():
            LOG.info("Start netserver with cmd: '%s'" % server_cmd)
            self.session.cmd_output_safe(server_cmd)

        if not wait.wait_for(self.is_server_running, 5):
            raise NetserverError("Can not start netperf server!")
        LOG.info("Netserver start successfully")

    def is_server_running(self):
        return self.is_target_running(os.path.basename(self.netserver_path))

    def stop(self):
        super(NetperfServer, self).stop(os.path.basename(self.netserver_path))


class NetperfClient(Netperf):

    def __init__(self, address, netperf_path, md5sum="", netperf_source="",
                 client="ssh", port="22", username="root", password="redhat",
                 prompt="^root@.*[\#\$]\s*$|", linesep="\n", status_test_command="echo $?",
                 compile_option="", install=True):
        """
        Init NetperfClient class.

        :param address: Remote host or guest address
        :param netperf_path: Remote netperf path
        :param me5sum: Local netperf package me5sum
        :param netperf_source: Netperf source file (path or link) which will
                               transfer to remote
        :param client: The client to use ('ssh', 'telnet' or 'nc')
        :param port: Port to connect to
        :param username: Username (if required)
        :param password: Password (if required)
        :param compile_option: Compile option for netperf
        :param install: Whether need install netperf or not.
        """
        super(NetperfClient, self).__init__(address, netperf_path, md5sum,
                                            netperf_source, client, port, username,
                                            password, prompt, linesep, status_test_command,
                                            compile_option, install)

    def start(self, server_address, test_option="", timeout=1200,
              cmd_prefix="", package_sizes=""):
        """
        Run netperf test

        :param server_address: Remote netserver address
        :param netperf_path: Netperf test option (global/test option)
        :param timeout: Netperf test timeout(-l)
        :param cmd_prefix: Prefix in netperf command
        :param package_sizes: Package sizes test in netperf command.
        :return: return test result
        """
        netperf_cmd = "%s %s -H %s %s " % (cmd_prefix, self.netperf_path,
                                           server_address, test_option)
        try:
            output = ""
            if package_sizes:
                for p_size in package_sizes.split():
                    cmd = netperf_cmd + " -- -m %s" % p_size
                    LOG.info("Start netperf with cmd: '%s'" % cmd)
                    output += self.session.cmd_output_safe(cmd,
                                                           timeout=timeout)
            else:
                LOG.info("Start netperf with cmd: '%s'" % netperf_cmd)
                output = self.session.cmd_output_safe(netperf_cmd,
                                                      timeout=timeout)
        except aexpect.ShellError as err:
            raise NetperfTestError("Run netperf error. %s" % str(err))
        self.result = output
        return self.result

    def bg_start(self, server_address, test_option="", session_num=1,
                 cmd_prefix="", package_sizes=""):
        """
        Run netperf background, for stress test do not have output

        :param server_address: Remote netserver address
        :param netperf_path: netperf test option (global/test option)
        :param timeout: Netperf test timeout(-l)
        :param cmd_prefix: Prefix in netperf command
        :param package_sizes: Package sizes test in netperf command.

        """
        if self.client == "nc":
            netperf_cmd = "start /b %s %s -H %s %s " % (cmd_prefix,
                                                        self.netperf_path,
                                                        server_address,
                                                        test_option)
        else:
            netperf_cmd = "%s %s -H %s %s " % (cmd_prefix,
                                               self.netperf_path,
                                               server_address,
                                               test_option)
        if package_sizes:
            for p_size in package_sizes.split():
                cmd = netperf_cmd + " -- -m %s" % p_size
                if self.client == "nc":
                    cmd = "%s > null " % cmd
                else:
                    cmd = "%s > /dev/null" % cmd
                txt = "Start %s sessions netperf background" % session_num
                txt += " with cmd: '%s' " % cmd
                LOG.info(txt)
                for num in xrange(int(session_num)):
                    self.session.cmd_output_safe("%s &" % cmd)
        else:
            if self.client == "nc":
                netperf_cmd = "%s > null " % netperf_cmd
            else:
                netperf_cmd = "%s > /dev/null " % netperf_cmd
            txt = "Start %s sessions netperf background" % session_num
            txt += " with cmd: '%s' " % netperf_cmd
            LOG.info(txt)
            for num in xrange(int(session_num)):
                self.session.cmd_output_safe("%s &" % netperf_cmd)

    def is_netperf_running(self):
        return self.is_target_running(os.path.basename(self.netperf_path))

    def stop(self):
        super(NetperfClient, self).stop(os.path.basename(self.netperf_path))
