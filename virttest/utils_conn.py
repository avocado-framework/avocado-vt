"""
connection tools to manage kinds of connection.
"""

import logging
import os
import shutil
import tempfile

import aexpect
from avocado.utils import path
from avocado.utils import process

from virttest import propcan, remote, utils_libvirtd
from virttest import data_dir
from virttest import utils_package
from virttest import libvirt_version


class ConnectionError(Exception):

    """
    The base error in connection.
    """
    pass


class ConnForbiddenError(ConnectionError):

    """
    Error in forbidden operation.
    """

    def __init__(self, detail):
        ConnectionError.__init__(self)
        self.detail = detail

    def __str__(self):
        return ('Operation is forbidden.\n'
                'Message: %s' % self.detail)


class ConnCopyError(ConnectionError):

    """
    Error in coping file.
    """

    def __init__(self, src_path, dest_path):
        ConnectionError.__init__(self)
        self.src_path = src_path
        self.dest_path = dest_path

    def __str__(self):
        return ('Copy file from %s to %s failed.'
                % (self.src_path, self.dest_path))


class ConnNotImplementedError(ConnectionError):

    """
    Error in calling unimplemented method
    """

    def __init__(self, method_type, class_type):
        ConnectionError.__init__(self)
        self.method_type = method_type
        self.class_type = class_type

    def __str__(self):
        return ('Method %s is not implemented in class %s\n'
                % (self.method_type, self.class_type))


class ConnLoginError(ConnectionError):

    """
    Error in login.
    """

    def __init__(self, dest, detail):
        ConnectionError.__init__(self)
        self.dest = dest
        self.detail = detail

    def __str__(self):
        return ("Got a error when login to %s.\n"
                "Error: %s\n" % (self.dest, self.detail))


class ConnToolNotFoundError(ConnectionError):

    """
    Error in not found tools.
    """

    def __init__(self, tool, detail):
        ConnectionError.__init__(self)
        self.tool = tool
        self.detail = detail

    def __str__(self):
        return ("Got a error when access the tool (%s).\n"
                "Error: %s\n" % (self.tool, self.detail))


class ConnSCPError(ConnectionError):

    """
    Error in SCP.
    """

    def __init__(self, src_ip, src_path, dest_ip, dest_path, detail):
        ConnectionError.__init__(self)
        self.src_ip = src_ip
        self.src_path = src_path
        self.dest_ip = dest_ip
        self.dest_path = dest_path
        self.detail = detail

    def __str__(self):
        return ("Failed scp from %s on %s to %s on %s.\n"
                "error: %s.\n" %
                (self.src_path, self.src_ip, self.dest_path,
                 self.dest_ip, self.detail))


class SSHCheckError(ConnectionError):

    """
    Base Error in check of SSH connection.
    """

    def __init__(self, server_ip, output):
        ConnectionError.__init__(self)
        self.server_ip = server_ip
        self.output = output

    def __str__(self):
        return ("SSH to %s failed.\n"
                "output: %s " % (self.server_ip, self.output))


class SSHRmAuthKeysError(ConnectionError):

    """
    Error in removing authorized_keys file.
    """

    def __init__(self, auth_keys, output):
        ConnectionError.__init__(self)
        self.auth_keys = auth_keys
        self.output = output

    def __str__(self):
        return ("Failed to remove authorized_keys file (%s).\n"
                "output: %s .\n" % (self.auth_keys, self.output))


class ConnCmdClientError(ConnectionError):

    """
    Error in executing cmd on client.
    """

    def __init__(self, cmd, output):
        ConnectionError.__init__(self)
        self.cmd = cmd
        self.output = output

    def __str__(self):
        return ("Execute command '%s' on client failed.\n"
                "output: %s" % (self.cmd, self.output))


class ConnPrivKeyError(ConnectionError):

    """
    Error in building private key with certtool command.
    """

    def __init__(self, key, output):
        ConnectionError.__init__(self)
        self.key = key
        self.output = output

    def __str__(self):
        return ("Failed to build private key file (%s).\n"
                "output: %s .\n" % (self.key, self.output))


class ConnCertError(ConnectionError):

    """
    Error in building certificate file with certtool command.
    """

    def __init__(self, cert, output):
        ConnectionError.__init__(self)
        self.cert = cert
        self.output = output

    def __str__(self):
        return ("Failed to build certificate file (%s).\n"
                "output: %s .\n" % (self.cert, self.output))


class ConnRmCertError(ConnectionError):

    """
    Error in removing certificate file with rm command.
    """

    def __init__(self, cert, output):
        ConnectionError.__init__(self)
        self.cert = cert
        self.output = output

    def __str__(self):
        return ("Failed to remove certificate file/path (%s).\n"
                "output: %s .\n" % (self.cert, self.output))


class ConnMkdirError(ConnectionError):

    """
    Error in making directory.
    """

    def __init__(self, directory, output):
        ConnectionError.__init__(self)
        self.directory = directory
        self.output = output

    def __str__(self):
        return ("Failed to make directory %s \n"
                "output: %s.\n" % (self.directory, self.output))


class ConnServerRestartError(ConnectionError):

    """
    Error in restarting libvirtd on server.
    """

    def __init__(self, output):
        ConnectionError.__init__(self)
        self.output = output

    def __str__(self):
        return ("Failed to restart libvirtd service on server.\n"
                "output: %s.\n" % (self.output))


class ConnectionBase(propcan.PropCanBase):

    """
    Base class of a connection between server and client.

    Connection is build to from client to server. And there are
    some information for server and client in ConnectionBase.
    """
    __slots__ = ('server_ip', 'server_user', 'server_pwd',
                 'client_ip', 'client_user', 'client_pwd',
                 'server_session', 'client_session',
                 'tmp_dir', 'auto_recover')

    def __init__(self, *args, **dargs):
        """
        Initialize instance with server info and client info.

        :param server_ip: Ip of server.
        :param server_user: Username to login server.
        :param server_pwd: Password for server_user.
        :param client_ip: IP of client.
        :param client_user: Username to login client.
        :param client_pwd: Password for client_user.
        :param server_session: Session to server and execute command on
                               server.
        :param client_session: Session to client and execute command on
                               client.
        :param tmp_dir: A tmp dir to store some tmp file.
        :param auto_recover: If it is False same as the default,
                             conn_recover() will not called by __del__()
                             If it is True, Connection class will call
                             conn_recover() in __del__(), then user need not
                             call it manually. But the errors in conn_recover()
                             will be ignored.

        Example:

        ::

          connection = ConnectionBase(server_ip=server_ip,
                                      server_user=server_user,
                                      server_pwd=server_pwd,
                                      client_ip=client_ip,
                                      client_user=client_user,
                                      client_pwd=client_pwd)
          connection.conn_setup()
          virsh.connect(URI)
          connection.conn_recover()

        We suggest *not* to pass auto_recover=True to __init__(),
        and call conn_recover() manually when you don't need this
        connection any more.
        """
        init_dict = dict(*args, **dargs)
        init_dict['server_ip'] = init_dict.get('server_ip', 'SERVER.IP')
        init_dict['server_user'] = init_dict.get('server_user', 'root')
        init_dict['server_pwd'] = init_dict.get('server_pwd', None)
        init_dict['client_ip'] = init_dict.get('client_ip', 'CLIENT.IP')
        init_dict['client_user'] = init_dict.get('client_user', 'root')
        init_dict['client_pwd'] = init_dict.get('client_pwd', None)
        init_dict['auto_recover'] = init_dict.get('auto_recover', False)
        super(ConnectionBase, self).__init__(init_dict)

        self.__dict_set__('client_session', None)
        self.__dict_set__('server_session', None)

        # make a tmp dir as a workspace
        tmp_dir = tempfile.mkdtemp(dir=data_dir.get_tmp_dir())
        if not os.path.isdir(tmp_dir):
            os.makedirs(tmp_dir)
        self.tmp_dir = tmp_dir

    def __del__(self):
        """
        Clean up any leftover sessions and tmp_dir.
        """
        try:
            self.close_session()
        finally:
            if self.auto_recover:
                try:
                    self.conn_recover()
                except ConnNotImplementedError:
                    pass
            tmp_dir = self.tmp_dir
            if (tmp_dir is not None) and (os.path.exists(tmp_dir)):
                shutil.rmtree(tmp_dir)

    def close_session(self):
        """
        If some session exists, close it down.
        """
        session_list = ['client_session', 'server_session']
        for session_name in session_list:
            session = self.__dict_get__(session_name)
            if session is not None:
                session.close()
            else:
                continue

    def conn_setup(self):
        """
        waiting for implemented by subclass.
        """
        raise ConnNotImplementedError('conn_setup', self.__class__)

    def conn_check(self):
        """
        waiting for implemented by subclass.
        """
        raise ConnNotImplementedError('conn_check', self.__class__)

    def conn_recover(self):
        """
        waiting for implemented by subclass.
        """
        raise ConnNotImplementedError('conn_recover', self.__class__)

    def _new_client_session(self):
        """
        Build a new client session.
        """
        transport = 'ssh'
        host = self.client_ip
        port = 22
        username = self.client_user
        password = self.client_pwd
        prompt = r"[\#\$]\s*$"
        try:
            client_session = remote.wait_for_login(transport, host, port,
                                                   username, password, prompt)
        except remote.LoginTimeoutError:
            raise ConnLoginError(host, "Got a timeout error when login to client.")
        except remote.LoginAuthenticationError:
            raise ConnLoginError(host, "Authentication failed to login to client.")
        except remote.LoginProcessTerminatedError:
            raise ConnLoginError(host, "Host terminates during login to client.")
        except remote.LoginError:
            raise ConnLoginError(host, "Some error occurs login to client failed.")

        return client_session

    def get_client_session(self):
        """
        If the client session exists,return it.
        else create a session to client and set client_session.
        """
        client_session = self.__dict_get__('client_session')

        if (client_session is not None) and (client_session.is_alive()):
            return client_session
        else:
            client_session = self._new_client_session()

        self.__dict_set__('client_session', client_session)
        return client_session

    def set_client_session(self, value):
        """
        Set client session to value.
        """
        if value:
            message = "Forbid to set client_session to %s." % value
        else:
            message = "Forbid to set client_session."

        raise ConnForbiddenError(message)

    def del_client_session(self):
        """
        Delete client session.
        """
        raise ConnForbiddenError('Forbid to del client_session')

    def _new_server_session(self):
        """
        Build a new server session.
        """
        transport = 'ssh'
        host = self.server_ip
        port = 22
        username = self.server_user
        password = self.server_pwd
        prompt = r"[\#\$]\s*$"
        try:
            server_session = remote.wait_for_login(transport, host, port,
                                                   username, password, prompt)
        except remote.LoginTimeoutError:
            raise ConnLoginError(host, "Got a timeout error when login to server.")
        except remote.LoginAuthenticationError:
            raise ConnLoginError(host, "Authentication failed to login to server.")
        except remote.LoginProcessTerminatedError:
            raise ConnLoginError(host, "Host terminates during login to server.")
        except remote.LoginError:
            raise ConnLoginError(host, "Some error occurs login to client server.")

        return server_session

    def get_server_session(self):
        """
        If the server session exists,return it.
        else create a session to server and set server_session.
        """
        server_session = self.__dict_get__('server_session')

        if (server_session is not None) and (server_session.is_alive()):
            return server_session
        else:
            server_session = self._new_server_session()

        self.__dict_set__('server_session', server_session)
        return server_session

    def set_server_session(self, value=None):
        """
        Set server session to value.
        """
        if value:
            message = "Forbid to set server_session to %s." % value
        else:
            message = "Forbid to set server_session."

        raise ConnForbiddenError(message)

    def del_server_session(self):
        """
        Delete server session.
        """
        raise ConnForbiddenError('Forbid to del server_session')


class SSHConnection(ConnectionBase):

    """
    Connection of SSH transport.

    Some specific variables in SSHConnection class.

    ssh_rsa_pub_path: Path of id_rsa.pub, default is /root/.ssh/id_rsa.pub.
    ssh_id_rsa_path: Path of id_rsa, default is /root/.ssh/id_rsa.
    SSH_KEYGEN, SSH_ADD, SSH_COPY_ID, SSH_AGENT, SHELL, SSH: tools to build
    a non-pwd connection.
    """
    __slots__ = ('ssh_rsa_pub_path', 'ssh_id_rsa_path', 'SSH_KEYGEN',
                 'SSH_ADD', 'SSH_COPY_ID', 'SSH_AGENT', 'SHELL', 'SSH',
                 'server_authorized_keys')

    def __init__(self, *args, **dargs):
        """
        Initialization of SSH connection.

        (1). Call __init__ of class ConnectionBase.
        (2). Initialize tools will be used in conn setup.
        """
        init_dict = dict(*args, **dargs)
        init_dict['ssh_rsa_pub_path'] = init_dict.get('ssh_rsa_pub_path',
                                                      '/root/.ssh/id_rsa.pub')
        init_dict['ssh_id_rsa_path'] = init_dict.get('ssh_id_rsa_path',
                                                     '/root/.ssh/id_rsa')
        super(SSHConnection, self).__init__(init_dict)
        # set the tool for ssh setup.
        tool_dict = {'SSH_KEYGEN': 'ssh-keygen',
                     'SSH_ADD': 'ssh-add',
                     'SSH_COPY_ID': 'ssh-copy-id',
                     'SSH_AGENT': 'ssh-agent',
                     'SHELL': 'sh',
                     'SSH': 'ssh'}

        for key in tool_dict:
            toolName = tool_dict[key]
            try:
                tool = path.find_command(toolName)
            except path.CmdNotFoundError:
                logging.debug("%s executable not set or found on path,"
                              "some function of connection will fail.",
                              toolName)
                tool = '/bin/true'
            self.__dict_set__(key, tool)

        self.server_authorized_keys = remote.RemoteFile(address=self.server_ip,
                                                        client='scp',
                                                        username=self.server_user,
                                                        password=self.server_pwd,
                                                        port='22',
                                                        remote_path='/root/.ssh/authorized_keys')

    def conn_check(self):
        """
        Check the SSH connection.

        (1).Initialize some variables.
        (2).execute ssh command to check conn.
        """
        client_session = self.client_session
        server_user = self.server_user
        server_ip = self.server_ip
        ssh = self.SSH
        if ssh == '/bin/true':
            raise ConnToolNotFoundError('ssh',
                                        "executable not set or found on path, ")

        cmd = "%s %s@%s exit 0" % (ssh, server_user, server_ip)
        try:
            client_session.cmd(cmd, timeout=5)
        except aexpect.ShellError as detail:
            client_session.close()
            raise SSHCheckError(server_ip, detail)
        logging.debug("Check the SSH to %s OK.", server_ip)

    def conn_recover(self):
        """
        Clean up authentication host.
        """
        # initialize variables
        server_ip = self.server_ip
        server_user = self.server_user
        server_pwd = self.server_pwd
        client_ip = self.client_ip

        server_session = remote.wait_for_login('ssh', server_ip, '22',
                                               server_user, server_pwd,
                                               r"[\#\$]\s*$")
        # Recover authorized_keys on server
        del self.server_authorized_keys

        # restart libvirtd service on server
        try:
            libvirtd_service = utils_libvirtd.Libvirtd(session=server_session)
            libvirtd_service.restart()
            server_session.close()
        except (remote.LoginError, aexpect.ShellError) as detail:
            server_session.close()
            raise ConnServerRestartError(detail)

        logging.debug("SSH authentication recover successfully.")

    def conn_setup(self, timeout=10):
        """
        Setup of SSH connection.

        (1).Initialization of some variables.
        (2).Check tools.
        (3).Initialization of id_rsa.
        (4).set a ssh_agent.
        (5).copy pub key to server.

        :param timeout: The time duration (in seconds) to wait for prompts
        """
        client_session = self.client_session
        ssh_rsa_pub_path = self.ssh_rsa_pub_path
        ssh_id_rsa_path = self.ssh_id_rsa_path
        server_user = self.server_user
        server_ip = self.server_ip
        server_pwd = self.server_pwd
        ssh_keygen = self.SSH_KEYGEN
        ssh_add = self.SSH_ADD
        ssh_copy_id = self.SSH_COPY_ID
        ssh_agent = self.SSH_AGENT
        shell = self.SHELL
        assert timeout >= 0, 'Invalid timeout value: %s' % timeout

        tool_dict = {'ssh_keygen': ssh_keygen,
                     'ssh_add': ssh_add,
                     'ssh_copy_id': ssh_copy_id,
                     'ssh_agent': ssh_agent,
                     'shell': shell}
        for tool_name in tool_dict:
            tool = tool_dict[tool_name]
            if tool == '/bin/true':
                raise ConnToolNotFoundError(tool_name,
                                            "executable not set or found on path,")

        if not client_session.cmd_status("ls /root/.ssh/id_rsa"):
            pass
        else:
            cmd = "%s -t rsa -f /root/.ssh/id_rsa -N '' " % (ssh_keygen)
            status, output = client_session.cmd_status_output(cmd)
            if status:
                raise ConnCmdClientError(cmd, output)

        cmd = "%s %s" % (ssh_agent, shell)
        status, output = client_session.cmd_status_output(cmd)
        if status:
            raise ConnCmdClientError(cmd, output)

        cmd = "%s %s" % (ssh_add, ssh_id_rsa_path)
        status, output = client_session.cmd_status_output(cmd)
        if status:
            raise ConnCmdClientError(cmd, output)

        cmd = "%s -i %s %s@%s" % (ssh_copy_id, ssh_rsa_pub_path,
                                  server_user, server_ip)
        client_session.sendline(cmd)
        try:
            remote.handle_prompts(client_session, server_user,
                                  server_pwd, prompt=r"[\#\$]\s*$", timeout=timeout)
        except remote.LoginError as detail:
            raise ConnCmdClientError(cmd, detail)

        client_session.close()
        logging.debug("SSH connection setup successfully.")


class TCPConnection(ConnectionBase):

    """
    Connection class for TCP transport.

    Some specific variables for TCPConnection class.
    """
    __slots__ = ('tcp_port', 'remote_syslibvirtd', 'sasl_type',
                 'remote_libvirtdconf', 'sasl_allowed_users',
                 'auth_tcp', 'listen_addr', 'remote_saslconf',
                 'remote_libvirtd_tcp_socket', 'client_hosts')

    def __init__(self, *args, **dargs):
        """
        init params for TCP connection and init tmp_dir.

        :param tcp_port: Port of tcp connection, default is 16509.
        :param sysconfig_libvirtd_path: Path of libvirtd file, default is
                                       ``/etc/sysconfig/libvirtd``.
        :param libvirtd_conf_path: Path of libvirtd.conf, default is
                                  ``/etc/libvirt/libvirtd.conf``.
        """
        init_dict = dict(*args, **dargs)
        init_dict['tcp_port'] = init_dict.get('tcp_port', '16509')
        init_dict['auth_tcp'] = init_dict.get('auth_tcp', 'none')
        init_dict['sasl_type'] = init_dict.get('sasl_type', 'gssapi')
        init_dict['listen_addr'] = init_dict.get('listen_addr')
        init_dict['sasl_allowed_users'] = init_dict.get('sasl_allowed_users')
        super(TCPConnection, self).__init__(init_dict)

        self.remote_syslibvirtd = remote.RemoteFile(
            address=self.server_ip,
            client='scp',
            username=self.server_user,
            password=self.server_pwd,
            port='22',
            remote_path='/etc/sysconfig/libvirtd')

        self.remote_libvirtdconf = remote.RemoteFile(
            address=self.server_ip,
            client='scp',
            username=self.server_user,
            password=self.server_pwd,
            port='22',
            remote_path='/etc/libvirt/libvirtd.conf')

        self.remote_libvirtd_tcp_socket = remote.RemoteFile(
            address=self.server_ip,
            client='scp',
            username=self.server_user,
            password=self.server_pwd,
            port='22',
            remote_path='/usr/lib/systemd/system/libvirtd-tcp.socket')

        self.remote_saslconf = remote.RemoteFile(
            address=self.server_ip,
            client='scp',
            username=self.server_user,
            password=self.server_pwd,
            port='22',
            remote_path='/etc/sasl2/libvirt.conf')

        self.client_hosts = remote.RemoteFile(
            address=self.client_ip,
            client='scp',
            username=self.client_user,
            password=self.client_pwd,
            port='22',
            remote_path='/etc/hosts')

    def conn_recover(self):
        """
        Clean up for TCP connection.

        (1).initialize variables.
        (2).Delete the RemoteFile.
        (3).restart libvirtd on server.
        """
        # initialize variables
        server_ip = self.server_ip
        server_user = self.server_user
        server_pwd = self.server_pwd
        # delete the RemoteFile object to recover remote file.
        del self.remote_syslibvirtd
        del self.remote_libvirtdconf
        del self.remote_saslconf
        del self.remote_libvirtd_tcp_socket
        del self.client_hosts

        # restart libvirtd service on server
        try:
            session = remote.wait_for_login('ssh', server_ip, '22',
                                            server_user, server_pwd,
                                            r"[\#\$]\s*$")
            libvirtd_service = utils_libvirtd.Libvirtd(session=session)
            if libvirt_version.version_compare(5, 6, 0, session):
                session.cmd("systemctl stop libvirtd.socket")
                libvirtd_service.stop()
                session.cmd("systemctl stop libvirtd-tcp.socket")
                session.cmd("systemctl daemon-reload")
                session.cmd("systemctl start libvirtd.socket")
                libvirtd_service.start()
            else:
                libvirtd_service.restart()
        except (remote.LoginError, aexpect.ShellError) as detail:
            raise ConnServerRestartError(detail)

        logging.debug("TCP connection recover successfully.")

    def conn_setup(self):
        """
        Enable tcp connect of libvirtd on server.

        (1).initialization for variables.
        (2).edit /etc/sysconfig/libvirtd on server.
        (3).edit /etc/libvirt/libvirtd.conf on server.
        (4).edit /usr/lib/systemd/system/libvirtd-tcp.socket on server for
            libvirt >= 5.6.
        (5).restart libvirtd service on server.
        """
        # initialize variables
        server_ip = self.server_ip
        server_user = self.server_user
        server_pwd = self.server_pwd
        tcp_port = self.tcp_port
        auth_tcp = self.auth_tcp
        server_session = self.server_session
        # require a list data type
        sasl_allowed_users = self.sasl_allowed_users
        listen_addr = self.listen_addr
        pattern_to_repl = {}
        if not libvirt_version.version_compare(5, 6, 0, server_session):
            # edit the /etc/sysconfig/libvirtd to add --listen args in libvirtd
            pattern_to_repl = {r".*LIBVIRTD_ARGS\s*=\s*\"\s*--listen\s*\".*":
                               "LIBVIRTD_ARGS=\"--listen\""}
            self.remote_syslibvirtd.sub_else_add(pattern_to_repl)

            # edit the /etc/libvirt/libvirtd.conf
            # listen_tcp=1, tcp_port=$tcp_port, auth_tcp="none"
            # listen_tcp=1, tcp_port=$tcp_port, auth_tcp=$auth_tcp
            pattern_to_repl = {r".*listen_tls\s*=.*": 'listen_tls=0',
                               r".*listen_tcp\s*=.*": 'listen_tcp=1',
                               r".*tcp_port\s*=.*": 'tcp_port="%s"' % (tcp_port),
                               r".*auth_tcp\s*=.*": 'auth_tcp="%s"' % (auth_tcp)}
        else:
            pattern_to_repl = {r".*auth_tcp\s*=.*": 'auth_tcp="%s"' % (auth_tcp)}
        # a whitelist of allowed SASL usernames, it's a list.
        # If the list is an empty, no client can connect
        if sasl_allowed_users:
            pattern_to_repl[r".*sasl_allowed_username_list\s*=.*"] = \
                'sasl_allowed_username_list=%s' % (sasl_allowed_users)
        if listen_addr:
            pattern_to_repl[r".*listen_addr\s*=.*"] = \
                "listen_addr='%s'" % (listen_addr)
        self.remote_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/sasl2/libvirt.conf to change sasl method
        # edit the /etc/hosts to add the host
        if self.sasl_type == 'gssapi':
            keytab = "keytab: /etc/libvirt/krb5.tab"
            if listen_addr:
                server_runner = remote.RemoteRunner(session=server_session)
                hostname = server_runner.run('hostname', ignore_status=True).stdout_text.strip()
                pattern_to_repl = {r".*%s.*" % listen_addr: "%s %s" % (listen_addr, hostname)}
                self.client_hosts.sub_else_add(pattern_to_repl)
        else:
            keytab = ""
        pattern_to_repl = {r".*mech_list\s*:\s*.*":
                           "mech_list: %s" % self.sasl_type,
                           r".*keytab\s*:\s*.*": keytab}
        self.remote_saslconf.sub_else_add(pattern_to_repl)

        if tcp_port != '16509' and libvirt_version.version_compare(5, 6, 0, server_session):
            pattern_to_repl = {r".*ListenStream\s*=.*": 'ListenStream=%s' % (tcp_port)}
            self.remote_libvirtd_tcp_socket.sub_else_add(pattern_to_repl)

        # restart libvirtd service on server
        try:
            session = remote.wait_for_login('ssh', server_ip, '22',
                                            server_user, server_pwd,
                                            r"[\#\$]\s*$")
            remote_runner = remote.RemoteRunner(session=session)
            remote_runner.run('iptables -F', ignore_status=True)
            libvirtd_service = utils_libvirtd.Libvirtd(session=session)
            # From libvirt 5.6, libvirtd is using systemd socket activation
            # by default
            if libvirt_version.version_compare(5, 6, 0, session):
                # Before start libvirtd-tcp.socket, user must stop libvirtd.
                # After libvirtd-tcp.socket is started, user mustn't start
                # libvirtd.
                session.cmd("systemctl stop libvirtd.socket")
                libvirtd_service.stop()
                session.cmd("systemctl daemon-reload")
                session.cmd("systemctl restart libvirtd-tcp.socket")
            else:
                libvirtd_service.restart()
        except (remote.LoginError, aexpect.ShellError) as detail:
            raise ConnServerRestartError(detail)

        logging.debug("TCP connection setup successfully.")


class TLSConnection(ConnectionBase):

    """
    Connection of TLS transport.

    Some specific variables for TLSConnection class.

    server_cn, client_cn, ca_cn: Info to build pki key.
    CERTOOL: tool to build key for TLS connection.
    pki_CA_dir: Dir to store CA key.
    libvirt_pki_dir, libvirt_pki_private_dir: Dir to store pki in libvirt.
    sysconfig_libvirtd_path, libvirtd_conf_path: Path of libvirt config file.
    hosts_path: /etc/hosts
    auth_tls, tls_port, listen_addr: custom TLS Auth, port and listen address
    tls_allowed_dn_list: DN's list are checked
    tls_verify_cert: disable verification, default is to always verify
    tls_sanity_cert: disable checks, default is to always run sanity checks
    custom_pki_path: custom pki path
    ca_cakey_path: CA certification path, sometimes need to reuse previous cert
    scp_new_cacert: copy new CA certification, default is to always copy
    restart_libvirtd: default is to restart libvirtd
    credential_dict: A dict for required file names in libvirt or qemu style
    qemu_tls: True for qemu native TLS support
    qemu_chardev_tls: True for config chardev tls in qemu conf
    """
    __slots__ = ('server_cn', 'client_cn', 'ca_cn', 'CERTTOOL', 'pki_CA_dir',
                 'libvirt_pki_dir', 'libvirt_pki_private_dir', 'client_hosts',
                 'server_libvirtdconf', 'server_syslibvirtd', 'auth_tls',
                 'tls_port', 'listen_addr', 'tls_allowed_dn_list', 'sasl_type',
                 'custom_pki_path', 'tls_verify_cert', 'tls_sanity_cert',
                 'ca_cakey_path', 'scp_new_cacert', 'restart_libvirtd',
                 'client_libvirtdconf', 'client_syslibvirtd', 'server_hosts',
                 'credential_dict', 'qemu_tls', 'qemu_chardev_tls',
                 'server_saslconf', 'server_qemuconf', 'client_qemuconf',
                 'server_libvirtd_tls_socket', 'client_libvirtd_tls_socket')

    def __init__(self, *args, **dargs):
        """
        Initialization of TLSConnection.

        (1).call the init func in ConnectionBase.
        (2).check and set CERTTOOL.
        (3).make a tmp directory as a workspace.
        (4).set values of pki related.
        """
        init_dict = dict(*args, **dargs)
        init_dict['server_cn'] = init_dict.get('server_cn', 'TLSServer')
        init_dict['client_cn'] = init_dict.get('client_cn', 'TLSClient')
        init_dict['ca_cn'] = init_dict.get('ca_cn', 'AUTOTEST.VIRT')
        init_dict['ca_cakey_path'] = init_dict.get('ca_cakey_path', None)
        init_dict['auth_tls'] = init_dict.get('auth_tls', 'none')
        init_dict['tls_port'] = init_dict.get('tls_port', '16514')
        init_dict['listen_addr'] = init_dict.get('listen_addr')
        init_dict['custom_pki_path'] = init_dict.get('custom_pki_path')
        init_dict['tls_verify_cert'] = init_dict.get('tls_verify_cert', 'yes')
        init_dict['tls_sanity_cert'] = init_dict.get('tls_sanity_cert', 'yes')
        init_dict['tls_allowed_dn_list'] = init_dict.get('tls_allowed_dn_list')
        init_dict['scp_new_cacert'] = init_dict.get('scp_new_cacert', 'yes')
        init_dict['sasl_type'] = init_dict.get('sasl_type', 'gssapi')
        init_dict['restart_libvirtd'] = init_dict.get(
            'restart_libvirtd', 'yes')

        super(TLSConnection, self).__init__(init_dict)
        # check and set CERTTOOL in slots
        try:
            CERTTOOL = path.find_command("certtool")
        except path.CmdNotFoundError:
            logging.warning("certtool executable not set or found on path, "
                            "TLS connection will not setup normally")
            CERTTOOL = '/bin/true'
        self.CERTTOOL = CERTTOOL

        self.qemu_tls = "yes" == init_dict.get('qemu_tls', 'no')
        self.qemu_chardev_tls = "yes" == init_dict.get('qemu_chardev_tls', 'no')
        delimeter = ''
        if self.qemu_tls or self.qemu_chardev_tls:
            delimeter = '-'

        self.credential_dict = {'cacert': 'ca%scert.pem' % delimeter,
                                'cakey': 'ca%skey.pem' % delimeter,
                                'servercert': 'server%scert.pem' % delimeter,
                                'serverkey': 'server%skey.pem' % delimeter,
                                'clientcert': 'client%scert.pem' % delimeter,
                                'clientkey': 'client%skey.pem' % delimeter}
        # set some pki related dir values
        if not self.custom_pki_path:
            self.pki_CA_dir = ('/etc/pki/CA/')
            self.libvirt_pki_dir = ('/etc/pki/libvirt/')
            self.libvirt_pki_private_dir = ('/etc/pki/libvirt/private/')
        else:
            # set custom certifications path
            dir_dict = {'CA': 'pki_CA_dir',
                        'libvirt': 'libvirt_pki_dir',
                        'libvirt/private': 'libvirt_pki_private_dir'}
            if not os.path.exists(self.custom_pki_path):
                os.makedirs(self.custom_pki_path)

            for dir_name in dir_dict:
                setattr(self, dir_dict[dir_name], self.custom_pki_path)

        self.server_qemuconf = remote.RemoteFile(
            address=self.server_ip,
            client='scp',
            username=self.server_user,
            password=self.server_pwd,
            port='22',
            remote_path='/etc/libvirt/qemu.conf')

        self.client_qemuconf = remote.RemoteFile(
            address=self.client_ip,
            client='scp',
            username=self.client_user,
            password=self.client_pwd,
            port='22',
            remote_path='/etc/libvirt/qemu.conf')

        self.client_hosts = remote.RemoteFile(
            address=self.client_ip,
            client='scp',
            username=self.client_user,
            password=self.client_pwd,
            port='22',
            remote_path='/etc/hosts')
        self.server_hosts = remote.RemoteFile(
            address=self.server_ip,
            client='scp',
            username=self.server_user,
            password=self.server_pwd,
            port='22',
            remote_path='/etc/hosts')

        self.server_syslibvirtd = remote.RemoteFile(
            address=self.server_ip,
            client='scp',
            username=self.server_user,
            password=self.server_pwd,
            port='22',
            remote_path='/etc/sysconfig/libvirtd')

        self.server_libvirtdconf = remote.RemoteFile(
            address=self.server_ip,
            client='scp',
            username=self.server_user,
            password=self.server_pwd,
            port='22',
            remote_path='/etc/libvirt/libvirtd.conf')

        self.server_saslconf = remote.RemoteFile(
            address=self.server_ip,
            client='scp',
            username=self.server_user,
            password=self.server_pwd,
            port='22',
            remote_path='/etc/sasl2/libvirt.conf')

        self.client_syslibvirtd = remote.RemoteFile(
            address=self.client_ip,
            client='scp',
            username=self.client_user,
            password=self.client_pwd,
            port='22',
            remote_path='/etc/sysconfig/libvirtd')

        self.client_libvirtdconf = remote.RemoteFile(
            address=self.client_ip,
            client='scp',
            username=self.client_user,
            password=self.client_pwd,
            port='22',
            remote_path='/etc/libvirt/libvirtd.conf')

        self.client_libvirtd_tls_socket = remote.RemoteFile(
            address=self.client_ip,
            client='scp',
            username=self.client_user,
            password=self.client_pwd,
            port='22',
            remote_path='/usr/lib/systemd/system/libvirtd-tls.socket')

        self.server_libvirtd_tls_socket = remote.RemoteFile(
            address=self.server_ip,
            client='scp',
            username=self.server_user,
            password=self.server_pwd,
            port='22',
            remote_path='/usr/lib/systemd/system/libvirtd-tls.socket')

    def conn_recover(self):
        """
        Do the clean up work.

        (1).initialize variables.
        (2).Delete remote file.
        (3).Restart libvirtd on server.
        """
        # clean up certifications firstly
        if self.auto_recover:
            self.cert_recover()

        # initialize variables
        server_ip = self.server_ip
        server_user = self.server_user
        server_pwd = self.server_pwd

        del self.client_hosts
        del self.server_syslibvirtd
        del self.server_libvirtdconf
        del self.server_qemuconf
        del self.server_hosts
        del self.server_saslconf
        del self.client_syslibvirtd
        del self.client_libvirtdconf
        del self.client_qemuconf
        del self.server_libvirtd_tls_socket
        del self.client_libvirtd_tls_socket

        # restart libvirtd service on server
        try:
            session = remote.wait_for_login('ssh', server_ip, '22',
                                            server_user, server_pwd,
                                            r"[\#\$]\s*$")
            libvirtd_service = utils_libvirtd.Libvirtd(session=session)
            if libvirt_version.version_compare(5, 6, 0, session):
                session.cmd("systemctl stop libvirtd.socket")
                libvirtd_service.stop()
                session.cmd("systemctl stop libvirtd-tls.socket")
                session.cmd("systemctl daemon-reload")
                session.cmd("systemctl start libvirtd.socket")
                libvirtd_service.start()
            else:
                libvirtd_service.restart()
        except (remote.LoginError, aexpect.ShellError) as detail:
            raise ConnServerRestartError(detail)
        logging.debug("TLS connection recover successfully.")

    def cert_recover(self):
        """
        Do the clean up certifications work.

        (1).initialize variables.
        (2).Delete local and remote generated certifications file.
        """
        # initialize variables
        server_ip = self.server_ip
        server_user = self.server_user
        server_pwd = self.server_pwd

        cert_dict = {'CA': '%s*' % self.pki_CA_dir,
                     'cert': self.libvirt_pki_dir,
                     'key': self.libvirt_pki_private_dir}

        # remove local generated certifications file
        for cert in cert_dict:
            cert_path = cert_dict[cert]
            cmd = "rm -rf %s" % cert_path
            if os.path.exists(cert_path):
                shutil.rmtree(cert_path)
            else:
                status, output = process.getstatusoutput(cmd)
                if status:
                    raise ConnRmCertError(cert_path, output)

        # remove remote generated certifications file
        server_session = remote.wait_for_login('ssh', server_ip, '22',
                                               server_user, server_pwd,
                                               r"[\#\$]\s*$")
        for cert in cert_dict:
            cert_path = cert_dict[cert]
            cmd = "rm -rf %s" % cert_path
            status, output = server_session.cmd_status_output(cmd)
            if status:
                raise ConnRmCertError(cert_path, output)

        server_session.close()
        logging.debug("TLS certifications recover successfully.")

    def conn_setup(self, server_setup=True, client_setup=True,
                   server_setup_local=False):
        """
        setup a TLS connection between server and client.
        At first check the certtool needed to setup.
        Then call some setup functions to complete connection setup.

        :param server_setup: True to setup TLS server on target host,
                             False to not setup
        :param client_setup: True to setup TLS client on source host,
                             False to not setup
        :param server_setup_local: True to setup TLS server on source host,
                             False to not setup
        """
        if self.CERTTOOL == '/bin/true':
            raise ConnToolNotFoundError('certtool',
                                        "certtool executable not set or found on path.")

        # support build multiple CAs with different CA CN
        build_CA(self.tmp_dir, self.ca_cn,
                 self.ca_cakey_path, self.CERTTOOL,
                 self.credential_dict)
        # not always need to setup CA, client and server together
        if server_setup:
            self.server_setup()
        if client_setup:
            self.client_setup()
        if server_setup_local:
            self.server_setup(on_local=True)

        self.close_session()
        logging.debug("TLS connection setup successfully.")

    def server_setup(self, on_local=False):
        """
        setup private key and certificate file for server.

        (1).initialization for variables.
        (2).build server key.
        (3).copy files to server.
        (4).edit /etc/sysconfig/libvirtd on server.
        (5).edit /etc/libvirt/libvirtd.conf on server.
        (6).restart libvirtd service on server.

        :param on_local: True to setup TLS server on source host,
                         otherwise not.
        """
        # initialize variables
        tmp_dir = self.tmp_dir
        scp_new_cacert = self.scp_new_cacert
        # sometimes, need to reuse previous CA cert
        if self.ca_cakey_path:
            cacert_path = os.path.join(self.ca_cakey_path, self.credential_dict['cacert'])
            cakey_path = os.path.join(self.ca_cakey_path, self.credential_dict['cakey'])
        else:
            cacert_path = os.path.join(tmp_dir, self.credential_dict['cacert'])
            cakey_path = os.path.join(tmp_dir, self.credential_dict['cakey'])

        serverkey_path = os.path.join(tmp_dir, self.credential_dict['serverkey'])
        servercert_path = os.path.join(tmp_dir, self.credential_dict['servercert'])

        # If need setup TLS server on source machine,
        # we need switch the machine information between source and target machines
        if on_local:
            server_ip = self.client_ip
            server_user = self.client_user
            server_pwd = self.client_pwd
            server_cn = self.client_cn
        else:
            server_ip = self.server_ip
            server_user = self.server_user
            server_pwd = self.server_pwd
            server_cn = self.server_cn

        auth_tls = self.auth_tls
        tls_port = self.tls_port
        listen_addr = self.listen_addr
        restart_libvirtd = self.restart_libvirtd
        tls_allowed_dn_list = self.tls_allowed_dn_list
        pki_path = self.custom_pki_path
        tls_verify_cert = self.tls_verify_cert
        tls_sanity_cert = self.tls_sanity_cert

        # build a server key.
        build_server_key(tmp_dir, self.ca_cakey_path,
                         server_cn, self.CERTTOOL,
                         self.credential_dict, on_local)

        # scp cacert.pem, servercert.pem and serverkey.pem to server.
        if on_local:
            server_session = self.client_session
        else:
            server_session = self.server_session
        if self.sasl_type == 'digest-md5':
            utils_package.package_install('cyrus-sasl-md5', session=server_session)
        cmd = "mkdir -p %s" % self.libvirt_pki_private_dir
        status, output = server_session.cmd_status_output(cmd)
        if status:
            raise ConnMkdirError(self.libvirt_pki_private_dir, output)

        if scp_new_cacert == 'no':
            scp_dict = {servercert_path: self.libvirt_pki_dir,
                        serverkey_path: self.libvirt_pki_private_dir}
        else:
            scp_dict = {cacert_path: self.pki_CA_dir,
                        cakey_path: self.pki_CA_dir,
                        servercert_path: self.libvirt_pki_dir,
                        serverkey_path: self.libvirt_pki_private_dir}

        for key in scp_dict:
            local_path = key
            remote_path = scp_dict[key]
            try:
                remote.copy_files_to(server_ip, 'scp', server_user,
                                     server_pwd, '22', local_path, remote_path)
            except remote.SCPError as detail:
                raise ConnSCPError('AdminHost', local_path,
                                   server_ip, remote_path, detail)
        # When qemu supports TLS, it needs not to modify below
        # configuration files, so simply return
        if self.qemu_tls:
            return

        # Ensure to use proper configuration objects
        if on_local:
            operate_libvirtdconf = self.client_libvirtdconf
            operate_syslibvirtd = self.client_syslibvirtd
            operate_libvirtd_tls_socket = self.client_libvirtd_tls_socket
            operate_qemuconf = self.server_qemuconf
        else:
            operate_libvirtdconf = self.server_libvirtdconf
            operate_syslibvirtd = self.server_syslibvirtd
            operate_libvirtd_tls_socket = self.server_libvirtd_tls_socket
            operate_qemuconf = self.client_qemuconf

        # Change qemu conf file to support tls for chardev
        if self.qemu_chardev_tls:
            pattern2repl = {r".*chardev_tls\s*=\s*.*":
                            "chardev_tls = 1"}
            operate_qemuconf.sub_else_add(pattern2repl)
            pattern2repl = {r".*chardev_tls_x509_cert_dir\s*="
                            r"\s*\"\/etc\/pki\/libvirt-chardev\s*\".*":
                            "chardev_tls_x509_cert_dir="
                            r"\"/etc/pki/libvirt-chardev\""}
            operate_qemuconf.sub_else_add(pattern2repl)

        if not libvirt_version.version_compare(5, 6, 0, server_session):
            # After libvirt 5.6.0, no need to set --listen for libvirt tls.
            # Instead, libvirt use socket file on target host to handle
            # the listen port.
            # Before libvirt 5.6.0, edit the /etc/sysconfig/libvirtd to add
            # --listen args in libvirtd
            pattern_to_repl = {r".*LIBVIRTD_ARGS\s*=\s*\"\s*--listen\s*\".*":
                               "LIBVIRTD_ARGS=\"--listen\""}
            operate_syslibvirtd.sub_else_add(pattern_to_repl)

            # edit the /etc/libvirt/libvirtd.conf to add listen_tls=1
            pattern_to_repl = {r".*listen_tls\s*=\s*.*": "listen_tls=1"}
            operate_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to add
        # listen_addr=$listen_addr
        if listen_addr:
            pattern_to_repl = {r".*listen_addr\s*=.*":
                               "listen_addr='%s'" % listen_addr}
            operate_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to add auth_tls=$auth_tls
        if auth_tls != 'none':
            pattern_to_repl = {r".*auth_tls\s*=\s*.*": 'auth_tls="%s"' % auth_tls}
            operate_libvirtdconf.sub_else_add(pattern_to_repl)
        elif libvirt_version.version_compare(5, 6, 0, server_session):
            pattern_to_repl = {r".*auth_tls\s*=\s*.*": 'auth_tls="none"'}
            operate_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to add tls_port=$tls_port
        if tls_port != '16514':
            if libvirt_version.version_compare(5, 6, 0, server_session):
                pattern_to_repl = {r".*ListenStream\s*=\s*.*": 'ListenStream=%s' % tls_port}
                operate_libvirtd_tls_socket.sub_else_add(pattern_to_repl)
            else:
                pattern_to_repl = {r".*tls_port\s*=\s*.*": 'tls_port="%s"' % tls_port}
                operate_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to add
        # tls_allowed_dn_list=$tls_allowed_dn_list
        if isinstance(tls_allowed_dn_list, list):
            pattern_to_repl = {r".*tls_allowed_dn_list\s*=\s*.*":
                               'tls_allowed_dn_list=%s' % tls_allowed_dn_list}
            operate_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to override
        # the default server certification file path
        if pki_path:
            cert_path_dict = {'ca_file': cacert_path,
                              'key_file': serverkey_path,
                              'cert_file': servercert_path}
            pattern_to_repl = {}
            for cert_name in cert_path_dict:
                cert_file = os.path.basename(cert_path_dict[cert_name])
                abs_cert_file = os.path.join(pki_path, cert_file)
                pattern_to_repl[r".*%s\s*=.*" % (cert_name)] = \
                    '%s="%s"' % (cert_name, abs_cert_file)
            operate_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to disable client verification
        if tls_verify_cert == "no":
            pattern_to_repl = {r".*tls_no_verify_certificate\s*=\s*.*":
                               'tls_no_verify_certificate=1'}
            operate_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to disable server sanity checks
        if tls_sanity_cert == "no":
            pattern_to_repl = {r".*tls_no_sanity_certificate\s*=\s*.*":
                               'tls_no_sanity_certificate=1'}
            operate_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/sasl2/libvirt.conf to change sasl method
        if self.sasl_type == 'gssapi':
            keytab = "keytab: /etc/libvirt/krb5.tab"
        else:
            keytab = ""
        pattern_to_repl = {r".*mech_list\s*:\s*.*":
                           "mech_list: %s" % self.sasl_type,
                           r".*keytab\s*:\s*.*": keytab}
        self.server_saslconf.sub_else_add(pattern_to_repl)

        # restart libvirtd service on server
        if restart_libvirtd == "yes":
            if on_local:
                libvirtd_service = utils_libvirtd.Libvirtd()
                # From libvirt 5.6, libvirtd is using systemd socket activation
                # by default
                if libvirt_version.version_compare(5, 6, 0):
                    process.run("systemctl stop libvirtd.socket")
                    libvirtd_service.stop()
                    process.run("systemctl daemon-reload")
                    process.run("systemctl start libvirtd.socket")
                    process.run("systemctl restart libvirtd-tls.socket")
                    libvirtd_service.start()
                else:
                    libvirtd_service.restart()
            else:
                try:
                    session = remote.wait_for_login('ssh', server_ip, '22',
                                                    server_user, server_pwd,
                                                    r"[\#\$]\s*$")
                    libvirtd_service = utils_libvirtd.Libvirtd(session=session)
                    if libvirt_version.version_compare(5, 6, 0, session):
                        session.cmd("systemctl stop libvirtd.socket")
                        libvirtd_service.stop()
                        session.cmd("systemctl daemon-reload")
                        session.cmd("systemctl start libvirtd.socket")
                        session.cmd("systemctl restart libvirtd-tls.socket")
                        libvirtd_service.start()
                    else:
                        libvirtd_service.restart()
                except (remote.LoginError, aexpect.ShellError) as detail:
                    raise ConnServerRestartError(detail)

        # edit /etc/hosts on remote host in case of connecting
        # from remote host to local host
        if not on_local:
            pattern_to_repl = {r".*%s.*" % self.client_cn:
                               "%s %s" % (self.client_ip, self.client_cn)}
            self.server_hosts.sub_else_add(pattern_to_repl)

    def client_setup(self):
        """
        setup private key and certificate file for client.

        (1).initialization for variables.
        (2).build a key for client.
        (3).copy files to client.
        (4).edit /etc/hosts on client.
        """
        # initialize variables
        tmp_dir = self.tmp_dir

        cacert_path = os.path.join(tmp_dir, self.credential_dict['cacert'])
        cakey_path = os.path.join(tmp_dir, self.credential_dict['cakey'])
        clientkey_path = os.path.join(tmp_dir, self.credential_dict['clientkey'])
        clientcert_path = os.path.join(tmp_dir, self.credential_dict['clientcert'])

        client_ip = self.client_ip
        client_user = self.client_user
        client_pwd = self.client_pwd

        # build a client key.
        build_client_key(tmp_dir, self.client_cn, self.CERTTOOL,
                         self.credential_dict)

        # scp cacert.pem, clientcert.pem and clientkey.pem to client.
        client_session = self.client_session
        if self.sasl_type == 'digest-md5':
            utils_package.package_install('cyrus-sasl-md5', session=client_session)
        for target_dir in [self.pki_CA_dir, self.libvirt_pki_private_dir]:
            if not os.path.exists(target_dir):
                cmd = "mkdir -p %s" % target_dir
                status, output = client_session.cmd_status_output(cmd)
                if status:
                    raise ConnMkdirError(target_dir, output)

        scp_dict = {cacert_path: self.pki_CA_dir,
                    cakey_path: self.pki_CA_dir,
                    clientcert_path: self.libvirt_pki_dir,
                    clientkey_path: self.libvirt_pki_private_dir}

        for key in scp_dict:
            local_path = key
            remote_path = scp_dict[key]
            try:
                remote.copy_files_to(client_ip, 'scp', client_user,
                                     client_pwd, '22', local_path, remote_path)
            except remote.SCPError as detail:
                raise ConnSCPError('AdminHost', local_path,
                                   client_ip, remote_path, detail)

        # edit /etc/hosts on client
        pattern_to_repl = {r".*%s.*" % self.server_cn:
                           "%s %s" % (self.server_ip, self.server_cn)}
        self.client_hosts.sub_else_add(pattern_to_repl)


def build_client_key(tmp_dir, client_cn="TLSClient", certtool="certtool",
                     credential_dict=None):
    """
    (1).initialization for variables.
    (2).make a private key with certtool command.
    (3).prepare a info file.
    (4).make a certificate file with certtool command.

    :param client_cn: cn for client info
    :param certtool: cert command
    :param credential_dict: A dict for credential files' names
    """
    # Initialize variables

    cakey_path = os.path.join(tmp_dir, credential_dict['cakey'])
    cacert_path = os.path.join(tmp_dir, credential_dict['cacert'])
    clientkey_path = os.path.join(tmp_dir, credential_dict['clientkey'])
    clientcert_path = os.path.join(tmp_dir, credential_dict['clientcert'])
    clientinfo_path = os.path.join(tmp_dir, 'client.info')

    # make a private key.
    cmd = "%s --generate-privkey > %s" % (certtool, clientkey_path)
    CmdResult = process.run(cmd, ignore_status=True, shell=True)
    if CmdResult.exit_status:
        raise ConnPrivKeyError(clientkey_path, CmdResult.stderr_text)

    # prepare a info file to build clientcert.
    clientinfo_file = open(clientinfo_path, "w")
    clientinfo_file.write("organization = AUTOTEST.VIRT\n")
    clientinfo_file.write("cn = %s\n" % (client_cn))
    clientinfo_file.write("tls_www_client\n")
    clientinfo_file.write("encryption_key\n")
    clientinfo_file.write("signing_key\n")
    clientinfo_file.close()

    # make a client certificate file and a client key file.
    cmd = ("%s --generate-certificate --load-privkey %s \
           --load-ca-certificate %s --load-ca-privkey %s \
           --template %s --outfile %s" %
           (certtool, clientkey_path, cacert_path,
            cakey_path, clientinfo_path, clientcert_path))
    CmdResult = process.run(cmd, ignore_status=True)
    if CmdResult.exit_status:
        raise ConnCertError(clientinfo_path, CmdResult.stderr_text)


def build_server_key(tmp_dir, ca_cakey_path=None,
                     server_cn="TLSServer", certtool="certtool",
                     credential_dict=None, on_local=False):
    """
    (1).initialization for variables.
    (2).make a private key with certtool command.
    (3).prepare a info file.
    (4).make a certificate file with certtool command.

    :param client_cn: cn for client info
    :param certtool: cert command
    :param credential_dict: A dict for credential files' names
    :param on_local: True to clean up old server key on source host
    """
    # initialize variables
    # sometimes, need to reuse previous CA cert
    if not ca_cakey_path:
        cakey_path = os.path.join(tmp_dir, credential_dict['cakey'])
        cacert_path = os.path.join(tmp_dir, credential_dict['cacert'])
    else:
        cakey_path = os.path.join(ca_cakey_path, credential_dict['cakey'])
        cacert_path = os.path.join(ca_cakey_path, credential_dict['cacert'])

    serverkey_path = os.path.join(tmp_dir, credential_dict['serverkey'])
    servercert_path = os.path.join(tmp_dir, credential_dict['servercert'])
    serverinfo_path = os.path.join(tmp_dir, 'server.info')

    if on_local:
        # delete serverkey.pem, servercert.pem and server.info
        # already created for remote host
        if os.path.exists(serverkey_path):
            os.remove(serverkey_path)
        if os.path.exists(servercert_path):
            os.remove(servercert_path)
        if os.path.exists(serverinfo_path):
            os.remove(serverinfo_path)

    # make a private key
    cmd = "%s --generate-privkey > %s" % (certtool, serverkey_path)
    cmd_result = process.run(cmd, ignore_status=True, shell=True)
    if cmd_result.exit_status:
        raise ConnPrivKeyError(serverkey_path, cmd_result.stderr_text)

    # prepare a info file to build servercert and serverkey
    serverinfo_file = open(serverinfo_path, "w")
    serverinfo_file.write("organization = AUTOTEST.VIRT\n")
    serverinfo_file.write("cn = %s\n" % (server_cn))
    serverinfo_file.write("tls_www_server\n")
    serverinfo_file.write("encryption_key\n")
    serverinfo_file.write("signing_key\n")
    serverinfo_file.close()

    # make a server certificate file and a server key file
    cmd = ("%s --generate-certificate --load-privkey %s \
           --load-ca-certificate %s --load-ca-privkey %s \
           --template %s --outfile %s" %
           (certtool, serverkey_path, cacert_path,
            cakey_path, serverinfo_path, servercert_path))
    CmdResult = process.run(cmd, ignore_status=True)
    if CmdResult.exit_status:
        raise ConnCertError(serverinfo_path, CmdResult.stderr_text)


def build_CA(tmp_dir, cn="AUTOTEST.VIRT", ca_cakey_path=None,
             certtool="certtool", credential_dict=None):
    """
    setup private key and certificate file which are needed to build.
    certificate file for client and server.

    (1).initialization for variables.
    (2).make a private key with certtool command.
    (3).prepare a info file.
    (4).make a certificate file with certtool command.
    :param tmp_dir: temp directory to store credentail files in
    :param cn: cn for CA info
    :param ca_cakey_path: path of CA key file
    :param certtool: cert command
    :param credential_dict: A dict for credential files' names
    """
    # initialize variables
    if not ca_cakey_path:
        cakey_path = os.path.join(tmp_dir, credential_dict['cakey'])
    else:
        cakey_path = os.path.join(ca_cakey_path, credential_dict['cakey'])
    cainfo_path = os.path.join(tmp_dir, 'ca.info')
    cacert_path = os.path.join(tmp_dir, credential_dict['cacert'])

    # make a private key
    # sometimes, may reuse previous CA cert, so don't always need to
    # generate private key
    if not ca_cakey_path:
        cmd = "%s --generate-privkey > %s " % (certtool, cakey_path)
        cmd_result = process.run(cmd, ignore_status=True, timeout=10, shell=True)
        if cmd_result.exit_status:
            raise ConnPrivKeyError(cakey_path, cmd_result.stderr_text)
    # prepare a info file to build certificate file
    cainfo_file = open(cainfo_path, "w")
    cainfo_file.write("cn = %s\n" % cn)
    cainfo_file.write("ca\n")
    cainfo_file.write("cert_signing_key\n")
    cainfo_file.close()

    # make a certificate file to build clientcert and servercert
    cmd = ("%s --generate-self-signed --load-privkey %s\
           --template %s --outfile %s" %
           (certtool, cakey_path, cainfo_path, cacert_path))
    CmdResult = process.run(cmd, ignore_status=True)
    if CmdResult.exit_status:
        raise ConnCertError(cainfo_path, CmdResult.stderr_text)


class UNIXConnection(ConnectionBase):

    """
    Connection class for UNIX transport.

    Some specific variables for UNIXConnection class.
    """
    __slots__ = ('auth_unix_ro', 'auth_unix_rw', 'unix_sock_dir',
                 'unix_sock_group', 'unix_sock_ro_perms',
                 'unix_sock_rw_perms', 'access_drivers',
                 'client_ip', 'client_user', 'client_pwd',
                 'client_libvirtdconf', 'restart_libvirtd',
                 'client_saslconf', 'client_hosts', 'sasl_type', 'libvirt_ver',
                 'sasl_allowed_username_list', 'client_libvirtd_socket',
                 'traditional_mode')

    def __init__(self, *args, **dargs):
        """
        init params for UNIX connection.

        :param auth_unix_ro: UNIX R/O sockets, default is 'none'.
        :param auth_unix_rw: UNIX R/W sockets, default is 'none'.
        :param unix_sock_group: UNIX domain socket group ownership,
                                default is 'libvirt'.
        :param access_drivers: access control restrictions,
                               default is '["polkit"]'.
        :param unix_sock_ro_perms: UNIX socket permissions for the
                                   R/O socket, default is '0777'.
        :param unix_sock_rw_perms: UNIX socket permissions for the
                                   R/W socket, default is '0770'.
        :param client_libvirtdconf: Path of client libvirtd.conf, default is
                                  '/etc/libvirt/libvirtd.conf'.
        :param restart_libvirtd: default is to restart libvirtd.
        """
        init_dict = dict(*args, **dargs)
        init_dict['auth_unix_ro'] = init_dict.get('auth_unix_ro', 'none')
        init_dict['auth_unix_rw'] = init_dict.get('auth_unix_rw', 'none')
        init_dict['sasl_type'] = init_dict.get('sasl_type', 'gssapi')
        init_dict['unix_sock_dir'] = init_dict.get(
            'unix_sock_dir', '/var/run/libvirt')
        init_dict['unix_sock_group'] = init_dict.get(
            'unix_sock_group', 'libvirt')
        init_dict['access_drivers'] = init_dict.get(
            'access_drivers', ["polkit"])
        init_dict['unix_sock_ro_perms'] = init_dict.get(
            'unix_sock_ro_perms', '0777')
        init_dict['unix_sock_rw_perms'] = init_dict.get(
            'unix_sock_rw_perms', '0770')
        init_dict['restart_libvirtd'] = init_dict.get(
            'restart_libvirtd', 'yes')
        init_dict['sasl_allowed_username_list'] = init_dict.get(
            'sasl_allowed_username_list', '["root/admin" ]')
        init_dict['traditional_mode'] = init_dict.get(
            'traditional_mode', 'no')

        super(UNIXConnection, self).__init__(init_dict)

        # Unable to get libvirt verion via libvirt_version.version_compare
        # once UNIX connection is setup, so set the value here.
        client_session = self.client_session
        self.libvirt_ver = libvirt_version.version_compare(5, 6, 0, client_session)

        self.client_libvirtdconf = remote.RemoteFile(
            address=self.client_ip,
            client='scp',
            username=self.client_user,
            password=self.client_pwd,
            port='22',
            remote_path='/etc/libvirt/libvirtd.conf')

        self.client_libvirtd_socket = remote.RemoteFile(
            address=self.client_ip,
            client='scp',
            username=self.client_user,
            password=self.client_pwd,
            port='22',
            remote_path='/usr/lib/systemd/system/libvirtd.socket')

        self.client_saslconf = remote.RemoteFile(
            address=self.client_ip,
            client='scp',
            username=self.client_user,
            password=self.client_pwd,
            port='22',
            remote_path='/etc/sasl2/libvirt.conf')

        self.client_hosts = remote.RemoteFile(
            address=self.client_ip,
            client='scp',
            username=self.client_user,
            password=self.client_pwd,
            port='22',
            remote_path='/etc/hosts')

    def conn_recover(self):
        """
        Do the clean up work.

        (1).Delete remote file.
        (2).Restart libvirtd on server.
        """
        traditional_mode = self.traditional_mode

        del self.client_libvirtdconf
        del self.client_saslconf
        del self.client_hosts
        del self.client_libvirtd_socket
        # restart libvirtd service on server
        client_session = self.client_session
        try:
            libvirtd_service = utils_libvirtd.Libvirtd(session=client_session)
            if self.libvirt_ver:
                # For traditional mode, need unmask libvirtd*.socket
                if traditional_mode == 'yes':
                    process.run("systemctl unmask libvirtd.socket", shell=True)
                    process.run("systemctl unmask libvirtd-admin.socket", shell=True)
                    process.run("systemctl unmask libvirtd-ro.socket", shell=True)
                    process.run("systemctl unmask libvirtd-tcp.socket", shell=True)
                    process.run("systemctl unmask libvirtd-tls.socket", shell=True)
                else:
                    process.run("systemctl daemon-reload", shell=True)
                    process.run("systemctl stop libvirtd.socket", shell=True)
                libvirtd_service.stop()
                process.run("systemctl start libvirtd.socket", shell=True)
                libvirtd_service.start()
            else:
                libvirtd_service.restart()
        except (remote.LoginError, aexpect.ShellError,
                process.CmdError) as detail:
            raise ConnServerRestartError(detail)

        logging.debug("UNIX connection recover successfully.")

    def conn_setup(self):
        """
        Setup a UNIX connection.

        (1).Initialize variables.
        (2).Update libvirtd.conf configuration.
        (3).Update libvirtd.socket for libvirt >= 5.6.
        (4).Restart libvirtd on client.
        """
        # initialize variables
        auth_unix_ro = self.auth_unix_ro
        auth_unix_rw = self.auth_unix_rw
        unix_sock_group = self.unix_sock_group
        unix_sock_dir = self.unix_sock_dir
        unix_sock_ro_perms = self.unix_sock_ro_perms
        unix_sock_rw_perms = self.unix_sock_rw_perms
        access_drivers = self.access_drivers
        restart_libvirtd = self.restart_libvirtd
        client_session = self.client_session
        sasl_allowed_username_list = self.sasl_allowed_username_list
        traditional_mode = self.traditional_mode

        # edit the /etc/libvirt/libvirtd.conf to add auth_unix_ro arg
        if auth_unix_ro:
            pattern_to_repl = {r".*auth_unix_ro\s*=.*":
                               'auth_unix_ro="%s"' % auth_unix_ro}
            self.client_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to add auth_unix_rw arg
        if auth_unix_rw:
            pattern_to_repl = {r".*auth_unix_rw\s*=.*":
                               'auth_unix_rw="%s"' % auth_unix_rw}
            self.client_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to add unix_sock_group arg
        if unix_sock_group != 'libvirt':
            pattern_to_repl = {r".*unix_sock_group\s*=.*":
                               'unix_sock_group="%s"' % unix_sock_group}
            self.client_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to add unix_sock_dir arg
        if unix_sock_dir != '/var/run/libvirt':
            if self.libvirt_ver:
                pattern_to_repl = {r".*ListenStream\s*=.*":
                                   'ListenStream=%s/libvirt-sock' % unix_sock_dir}
                self.client_libvirtd_socket.sub_else_add(pattern_to_repl)
            else:
                pattern_to_repl = {r".*unix_sock_dir\s*=.*":
                                   'unix_sock_dir="%s"' % unix_sock_dir}
                self.client_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to add access_drivers arg
        if access_drivers != ["polkit"]:
            pattern_to_repl = {r".*access_drivers\s*=.*":
                               'access_drivers="%s"' % access_drivers}
            self.client_libvirtdconf.sub_else_add(pattern_to_repl)

        if auth_unix_rw == 'sasl':
            pattern_to_repl = {r".*access_drivers\s*=.*":
                               '#access_drivers="%s"' % access_drivers}
            self.client_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to add unix_sock_ro_perms arg
        if unix_sock_ro_perms:
            pattern_to_repl = {r".*unix_sock_ro_perms\s*=.*":
                               'unix_sock_ro_perms="%s"' % unix_sock_ro_perms}
            self.client_libvirtdconf.sub_else_add(pattern_to_repl)

        # edit the /etc/libvirt/libvirtd.conf to add unix_sock_rw_perms arg
        if unix_sock_rw_perms:
            if self.libvirt_ver and traditional_mode == 'no':
                pattern_to_repl = {r".*SocketMode\s*=.*":
                                   'SocketMode=%s' % unix_sock_rw_perms}
                self.client_libvirtd_socket.sub_else_add(pattern_to_repl)
            else:
                pattern_to_repl = {r".*unix_sock_rw_perms\s*=.*":
                                   'unix_sock_rw_perms="%s"' % unix_sock_rw_perms}
                self.client_libvirtdconf.sub_else_add(pattern_to_repl)

        if self.sasl_type == 'digest-md5':
            utils_package.package_install('cyrus-sasl-md5', session=client_session)

        # edit the /etc/sasl2/libvirt.conf to change sasl method and
        # edit the /etc/hosts to add the host
        if self.sasl_type == 'gssapi' and auth_unix_rw == 'sasl':
            keytab = "keytab: /etc/libvirt/krb5.tab"
            sasldb = ""
            remote_runner = remote.RemoteRunner(session=client_session)
            hostname = remote_runner.run('hostname', ignore_status=True).stdout_text.strip()
            pattern_to_repl = {r".*127.0.0.1\s*.*":
                               "127.0.0.1    %s localhost localhost.localdomain "
                               "localhost4 localhost4.localdomain6" % hostname,
                               r".*::1\s*.*":
                               "::1    %s localhost localhost.localdomain "
                               "localhost6 localhost6.localdomain6" % hostname
                               }
            self.client_hosts.sub_else_add(pattern_to_repl)
            pattern_to_repl = {r".*sasl_allowed_username_list\s*=.*":
                               'sasl_allowed_username_list=%s' % sasl_allowed_username_list}
            self.client_libvirtdconf.sub_else_add(pattern_to_repl)
        else:
            keytab = ""
            sasldb = "sasldb_path: /etc/libvirt/passwd.db"
        pattern_to_repl = {r".*mech_list\s*:\s*.*":
                           "mech_list: %s" % self.sasl_type,
                           r".*keytab\s*:\s*.*": keytab,
                           r".*sasldb_path\s*:\s*.*": sasldb}
        self.client_saslconf.sub_else_add(pattern_to_repl)

        # restart libvirtd service on server
        if restart_libvirtd == "yes":
            try:
                libvirtd_service = utils_libvirtd.Libvirtd(
                    session=client_session)
                if self.libvirt_ver:
                    # For traditional mode, need mask libvirtd*.socket
                    if traditional_mode == 'yes':
                        process.run("systemctl stop libvirtd.socket", shell=True)
                        process.run("systemctl stop libvirtd-admin.socket", shell=True)
                        process.run("systemctl stop libvirtd-ro.socket", shell=True)
                        process.run("systemctl stop libvirtd-tcp.socket", shell=True)
                        process.run("systemctl stop libvirtd-tls.socket", shell=True)
                        libvirtd_service.stop()
                        process.run("systemctl mask libvirtd.socket", shell=True)
                        process.run("systemctl mask libvirtd-admin.socket", shell=True)
                        process.run("systemctl mask libvirtd-ro.socket", shell=True)
                        process.run("systemctl mask libvirtd-tcp.socket", shell=True)
                        process.run("systemctl mask libvirtd-tls.socket", shell=True)
                        process.run("systemctl daemon-reload", shell=True)
                    else:
                        process.run("systemctl stop libvirtd.socket", shell=True)
                        libvirtd_service.stop()
                        process.run("systemctl daemon-reload", shell=True)
                        process.run("systemctl start libvirtd.socket", shell=True)
                    libvirtd_service.start()
                else:
                    libvirtd_service.restart()
            except (remote.LoginError, aexpect.ShellError,
                    process.CmdError) as detail:
                raise ConnServerRestartError(detail)

        logging.debug("UNIX connection setup successfully.")
