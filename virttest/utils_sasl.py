"""
tools to manage sasl.
"""

import logging

import aexpect
from aexpect import remote

from avocado.core import exceptions
from avocado.utils import path
from avocado.utils import process

from virttest import propcan
from virttest import virsh


class SASL(propcan.PropCanBase):

    """
    Base class of a connection between server and client.
    """
    __slots__ = ("sasl_pwd_cmd", "sasl_user_pwd", "sasl_user_cmd",
                 "auto_recover", "linesep", "prompt", "session",
                 "server_ip", "server_user", "server_pwd",
                 "client", "port")

    def __init__(self, *args, **dargs):
        """
        Initialize instance
        """
        init_dict = dict(*args, **dargs)
        init_dict["sasl_pwd_cmd"] = path.find_command("saslpasswd2")
        init_dict["sasl_user_cmd"] = path.find_command("sasldblistusers2")
        init_dict["sasl_user_pwd"] = init_dict.get("sasl_user_pwd")
        init_dict["auto_recover"] = init_dict.get("auto_recover", False)
        init_dict["client"] = init_dict.get("client", "ssh")
        init_dict["port"] = init_dict.get("port", "22")
        init_dict["linesep"] = init_dict.get("linesep", "\n")
        init_dict["prompt"] = init_dict.get("prompt", r"[\#\$]\s*$")

        self.__dict_set__('session', None)
        super(SASL, self).__init__(init_dict)

    def __del__(self):
        """
        Close opened session and clear test environment
        """
        self.close_session()
        if self.auto_recover:
            try:
                self.cleanup()
            except Exception:
                raise exceptions.TestError(
                    "Failed to clean up test environment!")

    def _new_session(self):
        """
        Build a new server session.
        """
        port = self.port
        prompt = self.prompt
        host = self.server_ip
        client = self.client
        username = self.server_user
        password = self.server_pwd

        try:
            session = remote.wait_for_login(client, host, port,
                                            username, password, prompt)
        except remote.LoginTimeoutError:
            raise exceptions.TestError(
                "Got a timeout error when login to server.")
        except remote.LoginAuthenticationError:
            raise exceptions.TestError(
                "Authentication failed to login to server.")
        except remote.LoginProcessTerminatedError:
            raise exceptions.TestError(
                "Host terminates during login to server.")
        except remote.LoginError:
            raise exceptions.TestError(
                "Some error occurs login to client server.")
        return session

    def get_session(self):
        """
        Make sure the session is alive and available
        """
        session = self.__dict_get__('session')

        if (session is not None) and (session.is_alive()):
            return session
        else:
            session = self._new_session()

        self.__dict_set__('session', session)
        return session

    def close_session(self):
        """
        If session exists then close it
        """
        if self.session:
            self.session.close()

    def list_users(self, remote=True, sasldb_path="/etc/libvirt/passwd.db"):
        """
        List users in sasldb
        """
        cmd = "%s -f %s" % (self.sasl_user_cmd, sasldb_path)
        try:
            if remote:
                self.session = self.get_session()
                return self.session.cmd_output(cmd)
            else:
                return process.run(cmd).stdout_text
        except process.CmdError:
            logging.error("Failed to set a user's sasl password %s", cmd)

    def setup(self, remote=True):
        """
        Create sasl users with password
        """
        for sasl_user, sasl_pwd in eval(self.sasl_user_pwd):
            cmd = "echo %s |%s -p -a libvirt %s" % (sasl_pwd,
                                                    self.sasl_pwd_cmd,
                                                    sasl_user)
            try:
                if remote:
                    self.session = self.get_session()
                    self.session.cmd(cmd)
                else:
                    process.system(cmd)
            except process.CmdError:
                logging.error("Failed to set a user's sasl password %s", cmd)

    def cleanup(self, remote=True):
        """
        Clear created sasl users
        """
        for sasl_user, sasl_pwd in eval(self.sasl_user_pwd):
            cmd = "%s -a libvirt -d %s" % (self.sasl_pwd_cmd, sasl_user)
            try:
                if remote:
                    self.session = self.get_session()
                    self.session.cmd(cmd)
                else:
                    process.system(cmd)
            except process.CmdError:
                logging.error("Failed to disable a user's access %s", cmd)


class VirshSessionSASL(virsh.VirshSession):

    """
    A wrap class for virsh session which used SASL infrastructure.
    """

    def __init__(self, params):
        self.virsh_exec = virsh.VIRSH_EXEC
        self.sasl_user = params.get('sasl_user')
        self.sasl_pwd = params.get('sasl_pwd')
        self.remote_ip = params.get('remote_ip')
        self.remote_user = params.get('remote_user')
        self.remote_pwd = params.get('remote_pwd')
        self.remote_auth = False
        if self.remote_ip:
            self.remote_auth = True
        super(VirshSessionSASL, self).__init__(virsh_exec=self.virsh_exec,
                                               remote_ip=self.remote_ip,
                                               remote_user=self.remote_user,
                                               remote_pwd=self.remote_pwd,
                                               ssh_remote_auth=self.remote_auth,
                                               auto_close=True,
                                               check_libvirtd=False)
        self.sendline('connect')
        self.sendline(self.sasl_user)
        self.sendline(self.sasl_pwd)
        # make sure session is connected successfully
        if self.cmd_status('list', timeout=60) != 0:
            logging.debug("Persistent virsh session is not responding, "
                          "libvirtd may be dead.")
            raise aexpect.ShellStatusError(virsh.VIRSH_EXEC, 'list')
