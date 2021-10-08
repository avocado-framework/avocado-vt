"""
Functions and classes used for logging into guests and transferring files.
"""
from __future__ import division
from six import PY3
import logging
import time
import re
import os
import shutil
import tempfile

import aexpect
from aexpect.remote import *

from avocado.core import exceptions
from avocado.utils import process

from virttest import data_dir
from virttest import utils_logfile
from virttest.remote_commander import remote_master
from virttest.remote_commander import messenger

LOG = logging.getLogger('avocado.' + __name__)


def ssh_login_to_migrate(client, host, port, username, password, prompt, linesep="\n",
                         log_filename=None, log_function=None, timeout=10,
                         interface=None, identity_file=None,
                         status_test_command="echo $?", verbose=False, bind_ip=None,
                         preferred_authenticaton='password',
                         user_known_hosts_file='/dev/null'):
    """
    Log into a remote host (guest) using SSH (to be migrated).

    This wrapper is kept around to handle some additional SSH options like the
    preferred authentication and the known hosts file which were added while the
    PR to migrate the utility took about a year.

    :param client: The client to use ('ssh', 'telnet' or 'nc')
    :param host: Hostname or IP address
    :param port: Port to connect to
    :param username: Username (if required)
    :param password: Password (if required)
    :param prompt: Shell prompt (regular expression)
    :param linesep: The line separator to use when sending lines
            (e.g. '\\n' or '\\r\\n')
    :param log_filename: If specified, log all output to this file
    :param log_function: If specified, log all output using this function
    :param timeout: The maximal time duration (in seconds) to wait for
            each step of the login procedure (i.e. the "Are you sure" prompt
            or the password prompt)
    :param interface: The interface the neighbours attach to (only use when
                      using ipv6 linklocal address.)
    :param identity_file: Selects a file from which the identity (private key)
                          for public key authentication is read
    :param status_test_command: Command to be used for getting the last
            exit status of commands run inside the shell (used by
            cmd_status_output() and friends).
    :param bind_ip: ssh through specific interface on
                    client(specify interface ip)
    :param preferred_authenticaton: The preferred authentication of SSH connection
    :param user_known_hosts_file: one or more files to use for the user host key database
    :raise LoginError: If using ipv6 linklocal but not assign a interface that
                       the neighbour attache
    :raise LoginBadClientError: If an unknown client is requested
    :raise: Whatever handle_prompts() raises
    :return: A ShellSession object.
    """
    if client != "ssh":
        return remote_login(client, host, port, username, password, prompt,
                            linesep, log_filename, log_function, timeout,
                            interface, identity_file, status_test_command,
                            verbose, bind_ip)
    cmd = ("ssh %s -o UserKnownHostsFile=%s "
           "-o StrictHostKeyChecking=no -p %s" %
           ("-vv" if verbose else "", user_known_hosts_file, port))
    if bind_ip:
        cmd += (" -b %s" % bind_ip)
    if identity_file:
        cmd += (" -i %s" % identity_file)
    else:
        cmd += " -o PreferredAuthentications=%s" % preferred_authenticaton
    cmd += " %s@%s" % (username, host)

    if verbose:
        LOG.debug("Login command: '%s'", cmd)
    session = aexpect.ShellSession(cmd, linesep=linesep, prompt=prompt,
                                   status_test_command=status_test_command)
    try:
        handle_prompts(session, username, password, prompt, timeout)
    except Exception:
        session.close()
        raise
    if log_filename:
        log_file = utils_logfile.get_log_filename(log_filename)
        session.set_output_func(utils_logfile.log_line)
        session.set_output_params((log_file,))
        session.set_log_file(os.path.basename(log_file))
    return session


def wait_for_ssh_login_to_migrate(client, host, port, username, password, prompt,
                                  linesep="\n", log_filename=None, log_function=None,
                                  timeout=240, internal_timeout=10, interface=None,
                                  preferred_authenticaton='password'):
    """
    Make multiple attempts to log into a guest until one succeeds or timeouts.

    :param timeout: Total time duration to wait for a successful login
    :param internal_timeout: The maximum time duration (in seconds) to wait for
                             each step of the login procedure (e.g. the
                             "Are you sure" prompt or the password prompt)
    :interface: The interface the neighbours attach to
                (only use when using ipv6 linklocal address.)
    :see: remote_login()
    :raise: Whatever remote_login() raises
    :return: A RemoteSession object.
    """
    LOG.debug("Attempting to log into %s:%s using %s (timeout %ds)",
              host, port, client, timeout)
    end_time = time.time() + timeout
    verbose = False
    while time.time() < end_time:
        try:
            return ssh_login_to_migrate(client, host, port, username, password, prompt,
                                        linesep, log_filename, log_function,
                                        internal_timeout, interface, verbose=verbose,
                                        preferred_authenticaton=preferred_authenticaton)
        except LoginError as error:
            LOG.debug(error)
            verbose = True
        time.sleep(2)
    # Timeout expired; try one more time but don't catch exceptions
    if PY3:
        # 'preferred_authenticaton' is introduced in aexpect 1.6.1. In travis CI for python2.7,
        # it still uses aexpect 1.6.0 due to python2 compatibility problem, so E1123 will
        # be reported.
        # pylint: disable=E1123
        return remote_login(client, host, port, username, password, prompt,
                            linesep, log_filename, log_function,
                            internal_timeout, interface,
                            preferred_authenticaton=preferred_authenticaton)
    else:
        return remote_login(client, host, port, username, password, prompt,
                            linesep, log_filename, log_function,
                            internal_timeout, interface)


class AexpectIOWrapperOut(messenger.StdIOWrapperOutBase64):

    """
    Basic implementation of IOWrapper for stdout
    """

    def close(self):
        self._obj.close()

    def fileno(self):
        return os.open(self._obj, os.O_RDWR)

    def write(self, data):
        self._obj.send(data)


def remote_commander(client, host, port, username, password, prompt,
                     linesep="\n", log_filename=None, timeout=10, path=None):
    """
    Log into a remote host (guest) using SSH/Telnet/Netcat.

    :param client: The client to use ('ssh', 'telnet' or 'nc')
    :param host: Hostname or IP address
    :param port: Port to connect to
    :param username: Username (if required)
    :param password: Password (if required)
    :param prompt: Shell prompt (regular expression)
    :param linesep: The line separator to use when sending lines
            (e.g. '\\n' or '\\r\\n')
    :param log_filename: If specified, log all output to this file
    :param timeout: The maximal time duration (in seconds) to wait for
            each step of the login procedure (i.e. the "Are you sure" prompt
            or the password prompt)
    :param path: The path to place where remote_runner.py is placed.
    :raise LoginBadClientError: If an unknown client is requested
    :raise: Whatever handle_prompts() raises
    :return: A ShellSession object.
    """
    if path is None:
        path = data_dir.get_tmp_dir()
    if client == "ssh":
        cmd = ("ssh -o UserKnownHostsFile=/dev/null "
               "-o PreferredAuthentications=password "
               "-p %s %s@%s %s agent_base64" %
               (port, username, host, os.path.join(path, "remote_runner.py")))
    elif client == "telnet":
        cmd = "telnet -l %s %s %s" % (username, host, port)
    elif client == "nc":
        cmd = "nc %s %s" % (host, port)
    else:
        raise LoginBadClientError(client)

    LOG.debug("Login command: '%s'", cmd)
    session = aexpect.Expect(cmd, linesep=linesep)
    try:
        handle_prompts(session, username, password, prompt, timeout)
    except Exception:
        session.close()
        raise
    if log_filename:
        log_file = utils_logfile.get_log_filename(log_filename)
        session.set_output_func(utils_logfile.log_line)
        session.set_output_params((log_file,))
        session.set_log_file(os.path.basename(log_file))

    session.send_ctrl("raw")
    # Wrap io interfaces.
    inw = messenger.StdIOWrapperInBase64(session._get_fd("tail"))
    outw = AexpectIOWrapperOut(session)
    # Create commander

    cmd = remote_master.CommanderMaster(inw, outw, False)
    return cmd


def run_remote_cmd(cmd, params, remote_runner=None, ignore_status=True):
    """
    A function to run a command on remote host.

    :param cmd: the command to be executed
    :param params: the parameter for executing
    :param remote_runner: a remote runner object on remote host
    :param ignore_status: True - not raise exception when failed
                          False - raise exception when failed

    :return: CmdResult object
    :raise: exceptions.TestFail or exceptions.TestError
    """
    try:
        if not remote_runner:
            remote_ip = params.get("server_ip", params.get("remote_ip"))
            remote_pwd = params.get("server_pwd", params.get("remote_pwd"))
            remote_user = params.get("server_user", params.get("remote_user"))
            remote_runner = RemoteRunner(host=remote_ip,
                                         username=remote_user,
                                         password=remote_pwd)

        cmdresult = remote_runner.run(cmd, ignore_status=ignore_status)
        LOG.debug("Remote runner run result:\n%s", cmdresult)
        if cmdresult.exit_status and not ignore_status:
            raise exceptions.TestFail("Failed to run '%s' on remote: %s"
                                      % (cmd, cmdresult))
        return cmdresult
    except (LoginError, LoginTimeoutError,
            LoginAuthenticationError, LoginProcessTerminatedError) as e:
        LOG.error(e)
        raise exceptions.TestError(e)
    except process.CmdError as cmderr:
        LOG.error("Remote runner run failed:\n%s", cmderr)
        raise exceptions.TestFail("Failed to run '%s' on remote: %s"
                                  % (cmd, cmderr))


class Remote_Package(object):

    def __init__(self, address, client, username, password, port, remote_path):
        """
        Initialization of Remote Package class.

        :param address: Address of remote host(guest)
        :param client: The client to use ('ssh', 'telnet' or 'nc')
        :param username: Username (if required)
        :param password: Password (if required)
        :param port: Port to connect to
        :param remote_path: Remote package path
        """
        self.address = address
        self.client = client
        self.port = port
        self.username = username
        self.password = password
        self.remote_path = remote_path

        if self.client == "nc":
            self.cp_client = "rss"
            self.cp_port = 10023
        elif self.client == "ssh":
            self.cp_client = "scp"
            self.cp_port = 22
        else:
            raise LoginBadClientError(client)

    def pull_file(self, local_path, timeout=600):
        """
        Copy file from remote to local.
        """
        LOG.debug("Pull remote: '%s' to local: '%s'." % (self.remote_path,
                                                         local_path))
        copy_files_from(self.address, self.cp_client, self.username,
                        self.password, self.cp_port, self.remote_path,
                        local_path, timeout=timeout)

    def push_file(self, local_path, timeout=600):
        """
        Copy file from local to remote.
        """
        LOG.debug("Push local: '%s' to remote: '%s'." % (local_path,
                                                         self.remote_path))
        copy_files_to(self.address, self.cp_client, self.username,
                      self.password, self.cp_port, local_path,
                      self.remote_path, timeout=timeout)


class RemoteFile(object):

    """
    Class to handle the operations of file on remote host or guest.
    """

    def __init__(self, address, client, username, password, port,
                 remote_path, limit="", log_filename=None,
                 verbose=False, timeout=600):
        """
        Initialization of RemoteFile class.

        :param address: Address of remote host(guest)
        :param client: Type of transfer client
        :param username: Username (if required)
        :param password: Password (if required)
        :param remote_path: Path of file which we want to edit on remote.
        :param limit: Speed limit of file transfer.
        :param log_filename: If specified, log all output to this
                             file(SCP only)
        :param verbose: If True, log some stats using logging.debug (RSS only)
        :param timeout: The time duration (in seconds) to wait for the
                        transfer tocomplete.
        """
        self.address = address
        self.client = client
        self.username = username
        self.password = password
        self.port = port
        self.remote_path = remote_path
        self.limit = limit
        self.log_filename = log_filename
        self.verbose = verbose
        self.timeout = timeout

        # Get a local_path and all actions is taken on it.
        filename = os.path.basename(self.remote_path)

        # Get a local_path.
        tmp_dir = data_dir.get_tmp_dir()
        local_file = tempfile.NamedTemporaryFile(prefix=("%s_" % filename),
                                                 dir=tmp_dir)
        self.local_path = local_file.name
        local_file.close()

        # Get a backup_path.
        backup_file = tempfile.NamedTemporaryFile(prefix=("%s_" % filename),
                                                  dir=tmp_dir)
        self.backup_path = backup_file.name
        backup_file.close()

        # Get file from remote.
        try:
            self._pull_file()
        except SCPTransferFailedError:
            # Remote file doesn't exist, create empty file on local
            self._write_local([])

        # Save a backup.
        shutil.copy(self.local_path, self.backup_path)

    def __del__(self):
        """
        Called when the instance is about to be destroyed.
        """
        self._reset_file()
        if os.path.exists(self.backup_path):
            os.remove(self.backup_path)
        if os.path.exists(self.local_path):
            os.remove(self.local_path)

    def _pull_file(self):
        """
        Copy file from remote to local.
        """
        if self.client == "test":
            shutil.copy(self.remote_path, self.local_path)
        else:
            copy_files_from(self.address, self.client, self.username,
                            self.password, self.port, self.remote_path,
                            self.local_path, self.limit, self.log_filename,
                            self.verbose, self.timeout)

    def _push_file(self):
        """
        Copy file from local to remote.
        """
        if self.client == "test":
            shutil.copy(self.local_path, self.remote_path)
        else:
            copy_files_to(self.address, self.client, self.username,
                          self.password, self.port, self.local_path,
                          self.remote_path, self.limit, self.log_filename,
                          self.verbose, self.timeout)

    def _reset_file(self):
        """
        Copy backup from local to remote.
        """
        if self.client == "test":
            shutil.copy(self.backup_path, self.remote_path)
        else:
            copy_files_to(self.address, self.client, self.username,
                          self.password, self.port, self.backup_path,
                          self.remote_path, self.limit, self.log_filename,
                          self.verbose, self.timeout)

    def _read_local(self):
        """
        Read file on local_path.

        :return: string list got from readlines().
        """
        local_file = open(self.local_path, "r")
        lines = local_file.readlines()
        local_file.close()
        return lines

    def _write_local(self, lines):
        """
        Write file on local_path. Call writelines method of File.
        """
        local_file = open(self.local_path, "w")
        local_file.writelines(lines)
        local_file.close()

    def add(self, line_list, linesep=None):
        """
        Append lines in line_list into file on remote.

        :param line_list: string consists of lines
        :param linesep: end up with a separator
        """
        lines = self._read_local()
        for line in line_list:
            lines.append("\n%s" % line)
        if linesep is not None:
            lines[-1] += linesep
        self._write_local(lines)
        self._push_file()

    def sub(self, pattern2repl_dict):
        """
        Replace the string which match the pattern
        to the value contained in pattern2repl_dict.
        """
        lines = self._read_local()
        for pattern, repl in list(pattern2repl_dict.items()):
            for index in range(len(lines)):
                line = lines[index]
                lines[index] = re.sub(pattern, repl, line)
        self._write_local(lines)
        self._push_file()

    def truncate(self, length=0):
        """
        Truncate the detail of remote file to assigned length
        Content before
        line 1
        line 2
        line 3
        remote_file.truncate(length=1)
        Content after
        line 1

        :param length: how many lines you want to keep
        """
        lines = self._read_local()
        lines = lines[0: length]
        self._write_local(lines)
        self._push_file()

    def remove(self, pattern_list):
        """
        Remove the lines in remote file which matchs a pattern
        in pattern_list.

        :param pattern_list: pattern list to be matched
        """
        lines = self._read_local()
        for line in lines:
            for pattern in pattern_list:
                if re.match(pattern, line.rstrip('\n')):
                    lines.remove(line)
                    break
        self._write_local(lines)
        self._push_file()

    def sub_else_add(self, pattern2repl_dict):
        """
        Replace the string which match the pattern.
        If no match in the all lines, append the value
        to the end of file.
        """
        lines = self._read_local()
        for pattern, repl in list(pattern2repl_dict.items()):
            no_line_match = True
            for index in range(len(lines)):
                line = lines[index]
                if re.match(pattern, line):
                    no_line_match = False
                    lines[index] = re.sub(pattern, repl, line)
            if no_line_match:
                lines.append("\n%s" % repl)
        self._write_local(lines)
        self._push_file()


class RemoteRunner(object):

    """
    Class to provide a utils.run-like method to execute command on
    remote host or guest. Provide a similar interface with utils.run
    on local.
    """

    def __init__(self, client="ssh", host=None, port="22", username="root",
                 password=None, prompt=r"[\#\$]\s*$", linesep="\n",
                 log_filename=None, timeout=240, internal_timeout=10,
                 session=None, preferred_authenticaton='password',
                 log_function=None):
        """
        Initialization of RemoteRunner. Init a session login to remote host or
        guest.

        :param client: The client to use ('ssh', 'telnet' or 'nc')
        :param host: Hostname or IP address
        :param port: Port to connect to
        :param username: Username (if required)
        :param password: Password (if required)
        :param prompt: Shell prompt (regular expression)
        :param linesep: The line separator to use when sending lines
                (e.g. '\\n' or '\\r\\n')
        :param log_filename: If specified, log all output to this file
        :param timeout: Total time duration to wait for a successful login
        :param internal_timeout: The maximal time duration (in seconds) to wait
                for each step of the login procedure (e.g. the "Are you sure"
                prompt or the password prompt)
        :param session: An existing session
        :param preferred_authenticaton: The preferred authentication of SSH connection
        :param log_function: If specified, log all output using this function
        :see: wait_for_login()
        :raise: Whatever wait_for_login() raises
        """
        if session is None:
            if host is None:
                raise exceptions.TestError(
                    "Neither host, nor session was defined!")
            self.session = wait_for_ssh_login_to_migrate(client, host, port, username,
                                                         password, prompt, linesep,
                                                         log_filename, log_function,
                                                         timeout,
                                                         internal_timeout,
                                                         preferred_authenticaton=preferred_authenticaton)
        else:
            self.session = session
        # Init stdout pipe and stderr pipe.
        self.stdout_pipe = tempfile.mktemp()
        self.stderr_pipe = tempfile.mktemp()

    def run(self, command, timeout=60, ignore_status=False):
        """
        Method to provide a utils.run-like interface to execute command on
        remote host or guest.

        :param timeout: Total time duration to wait for command return.
        :param ignore_status: If ignore_status=True, do not raise an exception,
                              no matter what the exit code of the command is.
                              Else, raise CmdError if exit code of command is
                              not zero.
        """
        # Redirect the stdout and stderr to file, Deciding error message
        # from output, and taking off the color of output. To return the same
        # result with utils.run() function.
        command = "%s 1>%s 2>%s" % (
            command, self.stdout_pipe, self.stderr_pipe)
        status, _ = self.session.cmd_status_output(command, timeout=timeout)
        output = self.session.cmd_output("cat %s;rm -f %s" %
                                         (self.stdout_pipe, self.stdout_pipe))
        errput = self.session.cmd_output("cat %s;rm -f %s" %
                                         (self.stderr_pipe, self.stderr_pipe))
        cmd_result = process.CmdResult(command=command, exit_status=status,
                                       stdout=output, stderr=errput)
        cmd_result.stdout = cmd_result.stdout_text
        cmd_result.stderr = cmd_result.stderr_text
        if status and (not ignore_status):
            raise process.CmdError(command, cmd_result)
        return cmd_result


class VMManager(object):
    """Manage VM on remote host"""

    CMD_TIMEOUT = 240

    def __init__(self, params):
        self.remote_host = params.get("server_ip")
        self.remote_user = params.get("server_user")
        self.remote_pwd = params.get("server_pwd")
        self.vm_ip = params.get("vm_ip")
        self.vm_pwd = params.get("vm_pwd")
        self.vm_user = params.get("vm_user", 'root')
        self.port = params.get("port", 22)
        if not all([self.remote_host, self.remote_user, self.remote_pwd,
                    self.vm_ip, self.vm_pwd]):
            raise exceptions.TestError("At least one of [remote_host|"
                                       "remote_user|remote_pwd|vm_ip|"
                                       "vm_pwd] is invalid!")
        self.runner = RemoteRunner(host=self.remote_host,
                                   username=self.remote_user,
                                   password=self.remote_pwd)
        self.cmd_output = self.cmd_output_safe
        self.cmd = self.cmd_output_safe

    def setup_ssh_auth(self):
        """
        Setup SSH passwordless access between remote host
        and VM, which is on the remote host.
        """
        pri_key = '~/.ssh/id_rsa'
        pub_key = '~/.ssh/id_rsa.pub'
        # Check the private key and public key file on remote host.
        cmd = "ls %s %s" % (pri_key, pub_key)
        result = self.runner.run(cmd, ignore_status=True)
        if result.exit_status:
            LOG.debug("Create new SSH key pair")
            self.runner.run("ssh-keygen -t rsa -q -N '' -f %s" % pri_key)
        else:
            LOG.info("SSH key pair already exist")
        session = self.runner.session
        # To avoid the host key checking
        ssh_options = "%s %s" % ("-o UserKnownHostsFile=/dev/null",
                                 "-o StrictHostKeyChecking=no")
        session.sendline("ssh-copy-id %s -i %s root@%s"
                         % (ssh_options, pub_key, self.vm_ip))

        handle_prompts(session, self.vm_user, self.vm_pwd,
                       r"[\#\$]\s*$", debug=True)

    def check_network(self, count=5, timeout=60):
        """
        Check VM network connectivity

        :param count: counter to ping
        :param timeout: seconds to wait for
        """
        LOG.debug("Check VM network connectivity...")
        vm_net_connectivity = False
        sleep_time = 5
        result = ""
        cmd = "ping -c %s %s" % (count, self.vm_ip)
        while timeout > 0:
            result = self.runner.run(cmd, ignore_status=True)
            if result.exit_status:
                time.sleep(sleep_time)
                timeout -= sleep_time
                continue
            else:
                vm_net_connectivity = True
                LOG.info(result.stdout_text)
                break

        if not vm_net_connectivity:
            raise exceptions.TestFail("Failed to ping %s: %s"
                                      % (self.vm_ip, result.stdout_text))

    def run_command(self, command, runner=None, ignore_status=False, timeout=CMD_TIMEOUT):
        """
        Run command in the VM.

        :param command: The command to be executed in the VM
        :param runner: The runner to execute the command
        :param ignore_status: True, not raise an exception and
            will return CmdResult object. False, raise an exception
        :param timeout: Total time to wait for command return
        :raise: exceptions.TestFail, if the command fails
        :return: CmdResult object
        """
        ssh_options = "%s %s" % ("-o UserKnownHostsFile=/dev/null",
                                 "-o StrictHostKeyChecking=no")
        cmd = 'ssh %s %s@%s "%s"' % (ssh_options, self.vm_user,
                                     self.vm_ip, command)
        ret = None
        try:
            ret = self.runner.run(cmd, timeout=timeout, ignore_status=ignore_status)
        except process.CmdError as detail:
            LOG.debug("Failed to run '%s' in the VM: %s", cmd, detail)
            raise exceptions.TestFail("Failed to run '%s' in the VM: %s",
                                      cmd, detail)
        return ret

    def cmd_output_safe(self, cmd, timeout=CMD_TIMEOUT):
        """
        Unify the interface for session.cmd_output_safe()

        :param cmd: The command to execute
        :param timeout: Total time duration to wait for command return
        :return: cmd_result.stdout_text
        """
        return self.run_command(cmd, timeout=timeout).stdout_text.strip()

    def cmd_status(self, cmd, safe=True):
        """
        Unify the interface for session.cmd_status()

        :param cmd: The command to be executed
        :param safe: Ignored so far
        :return: cmd_result.exit_status
        """
        return self.run_command(cmd).exit_status

    def cmd_status_output(self, cmd, timeout=CMD_TIMEOUT):
        """
        Unify the interface for session.cmd_status_output()

        :param cmd: The command to be executed
        :param timeout: Total time duration to wait for command return
        :return: cmd_result.exit_status and cmd_result.stdout
        """
        ret = self.run_command(cmd, timeout=timeout)
        return (ret.exit_status, ret.stdout_text.strip())
