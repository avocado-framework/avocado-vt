# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# This code was imported from the avocado-vt project,
#
# virttest/remote.py
# Original author: Michael Goldish <mgoldish@redhat.com>
#
# Copyright: 2016 IBM
# Authors : Michael Goldish <mgoldish@redhat.com>

"""
Functions and classes used for logging into guests and transferring files.

Example usage:

::

    import aexpect
    import aexpect.remote

    with aexpect.ShellSession("sh") as b:
        b.cmd("echo asdf > /tmp/bbb")

    with aexpect.remote.remote_login("ssh", "127.0.0.1", 5000, "root", "123456",
                                    aexpect.remote.PROMPT_LINUX) as a:
        a.cmd("rm /tmp/aaa -Rf")
        aexpect.remote.scp_to_session(a, "/tmp/bbb", "/tmp/aaa")
        aexpect.remote.scp_from_session(a, "/tmp/aaa", "/tmp/ccc")

.. warning:: Some of this API is freshly migrated and might still be experimental.
"""

# disable too-many-* as we need them pylint: disable=R0912,R0913,R0914,R0915,C0302
# ..todo:: we could reduce the disabled issues after more significant refactoring

from __future__ import division
import logging
import time
import re
import os
import pipes


from remote_aexpect.client import Expect
from remote_aexpect.client import RemoteSession
from remote_aexpect.exceptions import ExpectTimeoutError
from remote_aexpect.exceptions import ExpectProcessTerminatedError
from remote_aexpect import rss_client


#: prompt to be used for shell sessions on linux machines (default)
PROMPT_LINUX = r"^\[.*\][\#\$]\s*$"
#: prompt to be used for shell sessions on windows machines
PROMPT_WINDOWS = r"^\w:\\.*>\s*$"


class RemoteError(Exception):
    """Base class for any remote error raised here."""


class LoginError(RemoteError):
    """Base class for any remote error related to login and session creation."""

    def __init__(self, msg, output=''):
        super().__init__()
        self.msg = msg
        self.output = output

    def __str__(self):
        return "%s    (output: %r)" % (self.msg, self.output)


class LoginAuthenticationError(LoginError):
    """Remote error related to login authentication problems."""


class LoginTimeoutError(LoginError):
    """Remote error related to login timeout expiration."""

    def __init__(self, output=''):
        super().__init__("Login timeout expired", output)


class LoginProcessTerminatedError(LoginError):
    """Remote error related to login process termination."""

    def __init__(self, status, output=''):
        super().__init__("Client process terminated", output)
        self.status = status

    def __str__(self):
        return ("%s    (status: %s,    output: %r)" %
                (self.msg, self.status, self.output))


class LoginBadClientError(LoginError):
    """Remote error related to unknown remote shell client."""

    def __init__(self, client):
        super().__init__('Unknown remote shell client')
        self.client = client

    def __str__(self):
        return "%s    (value: %r)" % (self.msg, self.client)


class TransferError(RemoteError):
    """Base class for any remote error related to data transfer."""

    def __init__(self, msg, output):
        super().__init__()
        self.msg = msg
        self.output = output

    def __str__(self):
        return "%s    (output: %r)" % (self.msg, self.output)


class TransferBadClientError(RemoteError):
    """Remote error related to unknown transfer client."""

    def __init__(self, client):
        super().__init__()
        self.client = client

    def __str__(self):
        return "Unknown file copy client: '%s', valid values are scp and rss" % self.client


class SCPError(TransferError):
    """Remote error related to transfer using SCP."""


class SCPAuthenticationError(SCPError):
    """Remote error related to transfer authentication using SCP."""


class SCPAuthenticationTimeoutError(SCPAuthenticationError):
    """Remote error related to transfer authentication timeout using SCP."""

    def __init__(self, output):
        super().__init__("Authentication timeout expired", output)


class SCPTransferTimeoutError(SCPError):
    """Remote error related to transfer timeout using SCP."""

    def __init__(self, output):
        super().__init__("Transfer timeout expired", output)


class SCPTransferFailedError(SCPError):
    """Remote error related to transfer failure using SCP."""

    def __init__(self, status, output):
        super().__init__(None, output)
        self.status = status

    def __str__(self):
        return ("SCP transfer failed    (status: %s,    output: %r)" %
                (self.status, self.output))


class NetcatError(TransferError):
    """Remote error related to transfer using netcat."""


class NetcatTransferTimeoutError(NetcatError):
    """Remote error related to transfer timeout using netcat."""

    def __init__(self, output):
        super().__init__("Transfer timeout expired", output)


class NetcatTransferFailedError(NetcatError):
    """Remote error related to transfer failure using netcat."""

    def __init__(self, status, output):
        super().__init__(None, output)
        self.status = status

    def __str__(self):
        return ("Netcat transfer failed    (status: %s,    output: %r)" %
                (self.status, self.output))


class NetcatTransferIntegrityError(NetcatError):
    """Remote error related to transfer integrity failure using netcat."""

    def __init__(self, output):
        super().__init__("Transfer integrity failed", output)


class UDPError(TransferError):
    """Remote error related to transfer using UDP."""

    def __init__(self, output):
        super().__init__("UDP transfer failed", output)


def quote_path(path):
    """
    Produce shell escaped version of string item or of list items, which are
    then joined by space.

    :param path: List or string
    :return: Shell escaped version
    """
    if isinstance(path, list):
        return ' '.join(map(pipes.quote, path))
    return pipes.quote(path)


def handle_prompts(session, username, password, prompt=PROMPT_LINUX,
                   timeout=10, debug=False):
    """
    Connect to a remote host (guest) using SSH or Telnet or else.

    Wait for questions and provide answers.  If timeout expires while
    waiting for output from the child (e.g. a password prompt or
    a shell prompt) -- fail.

    :param session: An Expect or RemoteSession instance to operate on
    :param username: The username to send in reply to a login prompt
    :param password: The password to send in reply to a password prompt
    :param prompt: The shell prompt that indicates a successful login
    :param timeout: The maximal time duration (in seconds) to wait for each
            step of the login procedure (i.e. the "Are you sure" prompt, the
            password prompt, the shell prompt, etc)
    :raise LoginTimeoutError: If timeout expires
    :raise LoginAuthenticationError: If authentication fails
    :raise LoginProcessTerminatedError: If the client terminates during login
    :raise LoginError: If some other error occurs
    :return: If connect succeed return the output text to script for further
             debug.
    """
    password_prompt_count = 0
    login_prompt_count = 0
    last_chance = False

    output = ""
    while True:
        try:
            match, text = session.read_until_last_line_matches(
                [r"[Aa]re you sure", r"[Pp]assword:\s*",
                 # Prompt of rescue mode for Red Hat.
                 r"\(or (press|type) Control-D to continue\):\s*$",
                 r"[Gg]ive.*[Ll]ogin:\s*$",  # Prompt of rescue mode for SUSE.
                 r"(?<![Ll]ast )[Ll]ogin:\s*$",  # Don't match "Last Login:"
                 r"[Cc]onnection.*closed", r"[Cc]onnection.*refused",
                 r"[Pp]lease wait", r"[Ww]arning", r"[Ee]nter.*username",
                 r"[Ee]nter.*password", r"[Cc]onnection timed out", prompt,
                 r"Escape character is.*",
                 r"Command>",
                 r"[Ll]ost connection"],
                timeout=timeout, internal_timeout=0.5)
            output += text
            if match == 0:  # "Are you sure you want to continue connecting"
                if debug:
                    logging.debug("Got 'Are you sure...', sending 'yes'")
                session.sendline("yes")
            elif match in [1, 2, 3, 10]:  # "password:"
                if password_prompt_count == 0:
                    if debug:
                        logging.debug("Got password prompt, sending '%s'",
                                      password)
                    session.sendline(password)
                    password_prompt_count += 1
                else:
                    raise LoginAuthenticationError("Got password prompt twice",
                                                   text)
            elif match in [4, 9]:  # "login:"
                if login_prompt_count == 0 and password_prompt_count == 0:
                    if debug:
                        logging.debug("Got username prompt; sending '%s'",
                                      username)
                    session.sendline(username)
                    login_prompt_count += 1
                else:
                    if login_prompt_count > 0:
                        msg = "Got username prompt twice"
                    else:
                        msg = "Got username prompt after password prompt"
                    raise LoginAuthenticationError(msg, text)
            elif match == 5:   # "Connection closed"
                raise LoginError("Client said 'connection closed'", text)
            elif match == 6:   # "Connection refused"
                raise LoginError("Client said 'connection refused'", text)
            elif match == 11:  # Connection timeout
                raise LoginError("Client said 'connection timeout'", text)
            elif match == 15:  # Connection lost
                raise LoginError("Disconnected to vm on remote host", text)
            elif match == 7:   # "Please wait"
                if debug:
                    logging.debug("Got 'Please wait'")
                timeout = 30
            elif match == 8:   # "Warning added RSA"
                if debug:
                    logging.debug("Got 'Warning added RSA to known host list")
            elif match == 12:  # prompt
                if debug:
                    logging.debug("Got shell prompt -- logged in")
                break
            elif match == 13:  # console prompt
                logging.debug("Got console prompt, send return to show login")
                session.sendline()
            elif match == 14:  # VMware vCenter command prompt
                # Some old vsphere version (e.x. 6.0.0) needs to enable first.
                cmd = 'shell.set --enabled True'
                logging.debug(
                    "Got VMware VCenter prompt, "
                    "send '%s' to enable shell first", cmd)
                session.sendline(cmd)
                logging.debug(
                    "Got VMware VCenter prompt, "
                    "send 'shell' to launch bash")
                session.sendline('shell')
        except ExpectTimeoutError as error:
            # sometimes, linux kernel print some message to console
            # the message maybe impact match login pattern, so send
            # a empty line to avoid unexpect login timeout
            if not last_chance:
                time.sleep(0.5)
                session.sendline()
                last_chance = True
            else:
                raise LoginTimeoutError(error.output) from error
        except ExpectProcessTerminatedError as error:
            raise LoginProcessTerminatedError(error.status, error.output) from error

    return output


def remote_login(client, host, port, username, password, prompt, linesep="\n",
                 log_filename=None, log_function=None, timeout=10,
                 interface=None, identity_file=None,
                 status_test_command="echo $?", verbose=False, bind_ip=None,
                 preferred_authenticaton='password',
                 user_known_hosts_file='/dev/null'):
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
    :param preferred_authenticaton: Given value of PreferredAuthentications in ssh
    :param user_known_hosts_file: Given value of UserKnownHostsFile in ssh
    :raise LoginError: If using ipv6 linklocal but not assign a interface that
                       the neighbour attache
    :raise LoginBadClientError: If an unknown client is requested
    :raise: Whatever handle_prompts() raises
    :return: A RemoteSession object.
    """
    verbose = "-vv" if verbose else ""
    if host and host.lower().startswith("fe80"):
        if not interface:
            raise RemoteError("When using ipv6 linklocal an interface must "
                              "be assigned")
        host = "%s%%%s" % (host, interface)
    if client == "ssh":
        cmd = ("ssh %s -o UserKnownHostsFile=%s "
               "-o StrictHostKeyChecking=no -p %s" %
               (verbose, user_known_hosts_file, port))
        if bind_ip:
            cmd += (" -b %s" % bind_ip)
        if identity_file:
            cmd += (" -i %s" % identity_file)
        else:
            cmd += " -o PreferredAuthentications=%s" % preferred_authenticaton
        cmd += " %s@%s" % (username, host)
    elif client == "telnet":
        cmd = "telnet -l %s %s %s" % (username, host, port)
    elif client == "nc":
        cmd = "nc %s %s %s" % (verbose, host, port)
    else:
        raise LoginBadClientError(client)

    if verbose:
        logging.debug("Login command: '%s'", cmd)
    session = RemoteSession(cmd, linesep=linesep, prompt=prompt,
                            status_test_command=status_test_command,
                            client=client, host=host, port=port,
                            username=username, password=password)
    try:
        handle_prompts(session, username, password, prompt, timeout)
    except Exception:
        session.close()
        raise
    if log_filename:
        session.set_output_func(log_function)
        session.set_output_params((log_filename,))
        session.set_log_file(os.path.basename(log_filename))
    return session


def wait_for_login(client, host, port, username, password, prompt,
                   linesep="\n", log_filename=None, log_function=None,
                   timeout=240, internal_timeout=10, interface=None,
                   preferred_authenticaton='password',
                   user_known_hosts_file='/dev/null'):
    """
    Make multiple attempts to log into a guest until one succeeds or timeouts.

    :param timeout: Total time duration to wait for a successful login
    :param internal_timeout: The maximum time duration (in seconds) to wait for
                             each step of the login procedure (e.g. the
                             "Are you sure" prompt or the password prompt)
    :param preferred_authenticaton: Given value of PreferredAuthentications in ssh
    :param user_known_hosts_file: Given value of UserKnownHostsFile in ssh
    :interface: The interface the neighbours attach to
                (only use when using ipv6 linklocal address.)
    :see: remote_login()
    :raise: Whatever remote_login() raises
    :return: A RemoteSession object.
    """
    logging.debug("Attempting to log into %s:%s using %s (timeout %ds)",
                  host, port, client, timeout)
    end_time = time.time() + timeout
    verbose = False
    while time.time() < end_time:
        try:
            return remote_login(client, host, port, username, password, prompt,
                                linesep, log_filename, log_function,
                                internal_timeout, interface, verbose=verbose,
                                preferred_authenticaton=preferred_authenticaton,
                                user_known_hosts_file=user_known_hosts_file)
        except LoginError as error:
            logging.debug(error)
            verbose = True
        time.sleep(2)
    # Timeout expired; try one more time but don't catch exceptions
    return remote_login(client, host, port, username, password, prompt,
                        linesep, log_filename, log_function,
                        internal_timeout, interface,
                        preferred_authenticaton=preferred_authenticaton,
                        user_known_hosts_file=user_known_hosts_file)


def _remote_scp(
        session, password_list, transfer_timeout=600, login_timeout=300):
    """
    Transfer files using SCP, given a command line.

    Transfer file(s) to a remote host (guest) using SCP.  Wait for questions
    and provide answers.  If login_timeout expires while waiting for output
    from the child (e.g. a password prompt), fail.  If transfer_timeout expires
    while waiting for the transfer to complete, fail.

    :param session: An Expect or RemoteSession instance to operate on
    :param password_list: Password list to send in reply to the password prompt
    :param transfer_timeout: The time duration (in seconds) to wait for the
            transfer to complete.
    :param login_timeout: The maximal time duration (in seconds) to wait for
            each step of the login procedure (i.e. the "Are you sure" prompt or
            the password prompt)
    :raise SCPAuthenticationError: If authentication fails
    :raise SCPTransferTimeoutError: If the transfer fails to complete in time
    :raise SCPTransferFailedError: If the process terminates with a nonzero
            exit code
    :raise SCPError: If some other error occurs
    """
    password_prompt_count = 0
    timeout = login_timeout
    authentication_done = False

    scp_type = len(password_list)

    while True:
        try:
            match, text = session.read_until_last_line_matches(
                [r"[Aa]re you sure", r"[Pp]assword:\s*$", r"lost connection"],
                timeout=timeout, internal_timeout=0.5)
            if match == 0:  # "Are you sure you want to continue connecting"
                logging.debug("Got 'Are you sure...', sending 'yes'")
                session.sendline("yes")
            elif match == 1:  # "password:"
                if password_prompt_count == 0:
                    logging.debug("Got password prompt, sending '%s'",
                                  password_list[password_prompt_count])
                    session.sendline(password_list[password_prompt_count])
                    password_prompt_count += 1
                    timeout = transfer_timeout
                    if scp_type == 1:
                        authentication_done = True
                elif password_prompt_count == 1 and scp_type == 2:
                    logging.debug("Got password prompt, sending '%s'",
                                  password_list[password_prompt_count])
                    session.sendline(password_list[password_prompt_count])
                    password_prompt_count += 1
                    timeout = transfer_timeout
                    authentication_done = True
                else:
                    raise SCPAuthenticationError("Got password prompt twice",
                                                 text)
            elif match == 2:  # "lost connection"
                raise SCPError("SCP client said 'lost connection'", text)
        except ExpectTimeoutError as error:
            if authentication_done:
                raise SCPTransferTimeoutError(error.output) from error
            raise SCPAuthenticationTimeoutError(error.output) from error
        except ExpectProcessTerminatedError as error:
            if error.status == 0:
                logging.debug("SCP process terminated with status 0")
                break
            raise SCPTransferFailedError(error.status, error.output) from error


def remote_scp(command, password_list, log_filename=None, log_function=None,
               transfer_timeout=600, login_timeout=300):
    """
    Transfer files using SCP, given a command line.

    :param command: The command to execute
        (e.g. "scp -r foobar root@localhost:/tmp/").
    :param password_list: Password list to send in reply to a password prompt.
    :param log_filename: If specified, log all output to this file
    :param log_function: If specified, log all output using this function
    :param transfer_timeout: The time duration (in seconds) to wait for the
            transfer to complete.
    :param login_timeout: The maximal time duration (in seconds) to wait for
            each step of the login procedure (i.e. the "Are you sure" prompt
            or the password prompt)
    :raise: Whatever _remote_scp() raises
    """
    logging.debug("Trying to SCP with command '%s', timeout %ss",
                  command, transfer_timeout)
    if log_filename:
        output_func = log_function
        output_params = (log_filename,)
    else:
        output_func = None
        output_params = ()
    with Expect(command, output_func=output_func,
                output_params=output_params) as session:
        _remote_scp(session, password_list, transfer_timeout, login_timeout)


def scp_to_remote(host, port, username, password, local_path, remote_path,
                  limit="", log_filename=None, log_function=None,
                  timeout=600, interface=None, directory=True):
    """
    Copy files to a remote host (guest) through scp.

    :param host: Hostname or IP address
    :param username: Username (if required)
    :param password: Password (if required)
    :param local_path: Path on the local machine where we are copying from
    :param remote_path: Path on the remote machine where we are copying to
    :param limit: Speed limit of file transfer.
    :param log_filename: If specified, log all output to this file
    :param log_function: If specified, log all output using this function
    :param timeout: The time duration (in seconds) to wait for the transfer
                    to complete.
    :param interface: The interface the neighbours attach to (only use when using
                      ipv6 linklocal address).
    :param directory: True to copy recursively if the directory to scp
    :raise: Whatever remote_scp() raises
    """
    if limit:
        limit = "-l %s" % (limit)

    if host and host.lower().startswith("fe80"):
        if not interface:
            raise SCPError("When using ipv6 linklocal address must assign",
                           "the interface the neighbour attache")
        host = "%s%%%s" % (host, interface)

    command = "scp"
    if directory:
        command = "%s -r" % command
    command += (r" -v -o UserKnownHostsFile=/dev/null "
                r"-o StrictHostKeyChecking=no "
                r"-o PreferredAuthentications=password %s "
                r"-P %s %s %s@\[%s\]:%s" %
                (limit, port, quote_path(local_path), username, host,
                 pipes.quote(remote_path)))
    password_list = []
    password_list.append(password)
    return remote_scp(command, password_list,
                      log_filename, log_function, timeout)


def scp_from_remote(host, port, username, password, remote_path, local_path,
                    limit="", log_filename=None, log_function=None,
                    timeout=600, interface=None, directory=True):
    """
    Copy files from a remote host (guest).

    :param host: Hostname or IP address
    :param username: Username (if required)
    :param password: Password (if required)
    :param local_path: Path on the local machine where we are copying from
    :param remote_path: Path on the remote machine where we are copying to
    :param limit: Speed limit of file transfer.
    :param log_filename: If specified, log all output to this file
    :param log_function: If specified, log all output using this function
    :param timeout: The time duration (in seconds) to wait for the transfer
                    to complete.
    :param interface: The interface the neighbours attach to (only use when
                      using ipv6 linklocal address).
    :param directory: True to copy recursively if the directory to scp
    :raise: Whatever remote_scp() raises
    """
    if limit:
        limit = "-l %s" % (limit)
    if host and host.lower().startswith("fe80"):
        if not interface:
            raise SCPError("When using ipv6 linklocal address must assign, ",
                           "the interface the neighbour attache")
        host = "%s%%%s" % (host, interface)

    command = "scp"
    if directory:
        command = "%s -r" % command
    command += (r" -v -o UserKnownHostsFile=/dev/null "
                r"-o StrictHostKeyChecking=no "
                r"-o PreferredAuthentications=password %s "
                r"-P %s %s@\[%s\]:%s %s" %
                (limit, port, username, host, quote_path(remote_path),
                 pipes.quote(local_path)))
    password_list = []
    password_list.append(password)
    remote_scp(command, password_list,
               log_filename, log_function, timeout)


def scp_between_remotes(src, dst, port, s_passwd, d_passwd, s_name, d_name,
                        s_path, d_path, limit="",
                        log_filename=None, log_function=None, timeout=600,
                        src_inter=None, dst_inter=None, directory=True):
    """
    Copy files from a remote host (guest) to another remote host (guest).

    :param src/dst: Hostname or IP address of src and dst
    :param s_name/d_name: Username (if required)
    :param s_passwd/d_passwd: Password (if required)
    :param s_path/d_path: Path on the remote machine where we are copying
                          from/to
    :param limit: Speed limit of file transfer.
    :param log_filename: If specified, log all output to this file
    :param log_function: If specified, log all output using this function
    :param timeout: The time duration (in seconds) to wait for the transfer
                    to complete.
    :param src_inter: The interface on local that the src neighbour attache
    :param dst_inter: The interface on the src that the dst neighbour attache
    :param directory: True to copy recursively if the directory to scp

    :return: True on success and False on failure.
    """
    if limit:
        limit = "-l %s" % (limit)
    if src and src.lower().startswith("fe80"):
        if not src_inter:
            raise SCPError("When using ipv6 linklocal address must assign ",
                           "the interface the neighbour attache")
        src = "%s%%%s" % (src, src_inter)
    if dst and dst.lower().startswith("fe80"):
        if not dst_inter:
            raise SCPError("When using ipv6 linklocal address must assign ",
                           "the interface the neighbour attache")
        dst = "%s%%%s" % (dst, dst_inter)

    command = "scp"
    if directory:
        command = "%s -r" % command
    command += (r" -v -o UserKnownHostsFile=/dev/null "
                r"-o StrictHostKeyChecking=no "
                r"-o PreferredAuthentications=password %s -P %s"
                r" %s@\[%s\]:%s %s@\[%s\]:%s" %
                (limit, port, s_name, src, quote_path(s_path), d_name, dst,
                 pipes.quote(d_path)))
    password_list = []
    password_list.append(s_passwd)
    password_list.append(d_passwd)
    return remote_scp(command, password_list,
                      log_filename, log_function, timeout)


def nc_copy_between_remotes(src, dst, s_port, s_passwd, d_passwd,
                            s_name, d_name, s_path, d_path,
                            c_type="ssh", c_prompt="\n",
                            d_port="8888", d_protocol="tcp", timeout=2,
                            check_sum=True, s_session=None,
                            d_session=None, file_transfer_timeout=600):
    """
    Copy files from guest to guest using netcat.

    This method only supports linux guest OS.

    :param src/dst: Hostname or IP address of src and dst
    :param s_name/d_name: Username (if required)
    :param s_passwd/d_passwd: Password (if required)
    :param s_path/d_path: Path on the remote machine where we are copying
    :param c_type: Login method to remote host(guest).
    :param c_prompt: command line prompt of remote host(guest)
    :param d_port:  the port data transfer
    :param d_protocol: nc protocol use (tcp or udp)
    :param timeout: If a connection and stdin are idle for more than timeout
                    seconds, then the connection is silently closed.
    :param s_session: A shell session object for source or None.
    :param d_session: A shell session object for dst or None.
    :param timeout: timeout for file transfer.

    :return: True on success and False on failure.
    """
    check_string = "NCFT"
    if not s_session:
        s_session = remote_login(c_type,
                                 src,
                                 s_port,
                                 s_name,
                                 s_passwd,
                                 c_prompt)
    if not d_session:
        d_session = remote_login(c_type,
                                 dst,
                                 s_port,
                                 d_name,
                                 d_passwd,
                                 c_prompt)

    try:
        s_session.cmd("iptables -I INPUT -p %s -j ACCEPT" % d_protocol)
        d_session.cmd("iptables -I OUTPUT -p %s -j ACCEPT" % d_protocol)
    except Exception:   # pylint: disable=W0703
        pass

    logging.info("Transfer data using netcat from %s to %s", src, dst)
    cmd = "nc -w %s" % timeout
    if d_protocol == "udp":
        cmd += " -u"
    receive_cmd = ("echo %s | %s -l %s > %s" %
                   (check_string, cmd, d_port, d_path))
    d_session.sendline(receive_cmd)
    send_cmd = "%s %s %s < %s" % (cmd, dst, d_port, s_path)
    status, output = s_session.cmd_status_output(
        send_cmd, timeout=file_transfer_timeout)
    if status:
        err = "Fail to transfer file between %s -> %s." % (src, dst)
        if check_string not in output:
            err += ("src did not receive check "
                    "string %s sent by dst." % check_string)
        err += "send nc command %s, output %s" % (send_cmd, output)
        err += "Receive nc command %s." % receive_cmd
        raise NetcatTransferFailedError(status, err)

    if check_sum:
        logging.info("md5sum cmd = md5sum %s", s_path)
        output = s_session.cmd("md5sum %s" % s_path)
        src_md5 = output.split()[0]
        dst_md5 = d_session.cmd("md5sum %s" % d_path).split()[0]
        if src_md5.strip() != dst_md5.strip():
            err_msg = ("Files md5sum mismatch, "
                       "file %s md5sum is '%s', "
                       "but the file %s md5sum is %s" %
                       (s_path, src_md5, d_path, dst_md5))
            raise NetcatTransferIntegrityError(err_msg)
    return True


def udp_copy_between_remotes(src, dst, s_port, s_passwd, d_passwd,
                             s_name, d_name, s_path, d_path,
                             c_type="ssh", c_prompt="\n",
                             d_port="9000", timeout=600):
    """
    Copy files from guest to guest using udp.

    :param src/dst: Hostname or IP address of src and dst
    :param s_name/d_name: Username (if required)
    :param s_passwd/d_passwd: Password (if required)
    :param s_path/d_path: Path on the remote machine where we are copying
    :param c_type: Login method to remote host(guest).
    :param c_prompt: command line prompt of remote host(guest)
    :param d_port:  the port data transfer
    :param timeout: data transfer timeout
    """
    s_session = remote_login(c_type, src, s_port, s_name, s_passwd, c_prompt)
    d_session = remote_login(c_type, dst, s_port, d_name, d_passwd, c_prompt)

    def get_abs_path(session, filename, extension):
        """Return file path drive+path."""
        cmd_tmp = "wmic datafile where \"Filename='%s' and "
        cmd_tmp += "extension='%s'\" get drive^,path"
        cmd = cmd_tmp % (filename, extension)
        info = session.cmd_output(cmd, timeout=360).strip()
        drive_path = re.search(r'(\w):\s+(\S+)', info, re.M)
        if not drive_path:
            raise UDPError("Not found file %s.%s in your guest"
                           % (filename, extension))
        return ":".join(drive_path.groups())

    def get_file_md5(session, file_path):
        """Get files md5sums."""
        if c_type == "ssh":
            md5_cmd = "md5sum %s" % file_path
            md5_reg = r"(\w+)\s+%s.*" % file_path
        else:
            drive_path = get_abs_path(session, "md5sums", "exe")
            filename = file_path.split("\\")[-1]
            md5_reg = r"%s\s+(\w+)" % filename
            md5_cmd = '%smd5sums.exe %s | find "%s"' % (drive_path, file_path,
                                                        filename)
        output = session.cmd_output(md5_cmd)
        file_md5 = re.findall(md5_reg, output)
        if not output:
            raise UDPError("Get file %s md5sum error" % file_path)
        return file_md5

    def server_alive(session):
        """Check if server is alive."""
        if c_type == "ssh":
            check_cmd = "ps aux"
        else:
            check_cmd = "tasklist"
        output = session.cmd_output(check_cmd)
        if not output:
            raise UDPError("Can not get the server status")
        if "sendfile" in output.lower():
            return True
        return False

    def start_server(session):
        """Start the server."""
        if c_type == "ssh":
            start_cmd = "sendfile %s &" % d_port
        else:
            drive_path = get_abs_path(session, "sendfile", "exe")
            start_cmd = "start /b %ssendfile.exe %s" % (drive_path,
                                                        d_port)
        session.cmd_output_safe(start_cmd)
        if not server_alive(session):
            raise UDPError("Start udt server failed")

    def start_client(session):
        """Start the client."""
        if c_type == "ssh":
            client_cmd = "recvfile %s %s %s %s" % (src, d_port,
                                                   s_path, d_path)
        else:
            drive_path = get_abs_path(session, "recvfile", "exe")
            client_cmd_tmp = "%srecvfile.exe %s %s %s %s"
            client_cmd = client_cmd_tmp % (drive_path, src, d_port,
                                           s_path.split("\\")[-1],
                                           d_path.split("\\")[-1])
        session.cmd_output_safe(client_cmd, timeout)

    def stop_server(session):
        """Stop the server."""
        if c_type == "ssh":
            stop_cmd = "killall sendfile"
        else:
            stop_cmd = "taskkill /F /IM sendfile.exe"
        if server_alive(session):
            session.cmd_output_safe(stop_cmd)

    try:
        src_md5 = get_file_md5(s_session, s_path)
        if not server_alive(s_session):
            start_server(s_session)
        start_client(d_session)
        dst_md5 = get_file_md5(d_session, d_path)
        if src_md5 != dst_md5:
            err_msg = ("Files md5sum mismatch, "
                       "file %s md5sum is '%s', "
                       "but the file %s md5sum is %s" %
                       (s_path, src_md5, d_path, dst_md5))
            raise UDPError(err_msg)
    finally:
        stop_server(s_session)
        s_session.close()
        d_session.close()


def login_from_session(session, log_filename=None, log_function=None,
                       timeout=240, internal_timeout=10, interface=None):
    """
    Log in remotely and return a session for the connection with the same
    configuration as a previous session.

    :param session: an SSH session whose configuration will be reused
    :type session: RemoteSession object
    :returns: connection session
    :rtype: RemoteSession object

    The rest of the arguments are identical to wait_for_login().
    """
    return wait_for_login(session.client, session.host, session.port,
                          session.username, session.password,
                          session.prompt, session.linesep,
                          log_filename, log_function,
                          timeout, internal_timeout, interface)


def scp_to_session(session, local_path, remote_path,
                   limit="", log_filename=None, log_function=None,
                   timeout=600, interface=None, directory=True):
    """
    Secure copy a filepath (w/o wildcard) to a remote location with the same
    configuration as a previous session.

    :param session: an SSH session whose configuration will be reused
    :type session: RemoteSession object
    :param str local_path: local filepath to copy from
    :param str remote_path: remote filepath to copy to

    The rest of the arguments are identical to scp_to_remote().
    """
    scp_to_remote(session.host, session.port,
                  session.username, session.password,
                  local_path, remote_path,
                  limit, log_filename, log_function,
                  timeout, interface, directory)


def scp_from_session(session, remote_path, local_path,
                     limit="", log_filename=None, log_function=None,
                     timeout=600, interface=None, directory=True):
    """
    Secure copy a filepath (w/o wildcard) from a remote location with the same
    configuration as a previous session.

    :param session: an SSH session whose configuration will be reused
    :type session: RemoteSession object
    :param str remote_path: remote filepath to copy from
    :param str local_path: local filepath to copy to

    The rest of the arguments are identical to scp_from_remote().
    """
    scp_from_remote(session.host, session.port,
                    session.username, session.password,
                    remote_path, local_path,
                    limit, log_filename, log_function,
                    timeout, interface, directory)


def throughput_transfer(func):
    """
    wrapper function for copy_files_to/copy_files_from function, will
    print throughput if filesize is not none, else will print elapsed time
    """
    def transfer(*args, **kwargs):
        """Wrapper transfer function."""
        if "from" in func.__name__:
            msg = (
                "Copy file from %s:%s to %s, " %
                (args[0], args[5], args[6]))
        else:
            msg = (
                "Copy file from %s to %s:%s, " %
                (args[5], args[0], args[6]))
        start_time = time.time()
        ret = func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        if kwargs.get("fileszie", None) is not None:
            throughput = kwargs["filesize"] / elapsed_time
            msg += "estimated throughput: %.2f MB/s" % throughput
        else:
            msg += "elapsed time: %s" % elapsed_time
        logging.info(msg)
        return ret
    return transfer


@throughput_transfer
def copy_files_to(address, client, username, password, port, local_path,
                  remote_path, limit="", log_filename=None, log_function=None,
                  verbose=False, timeout=600, interface=None, filesize=None,  # pylint: disable=unused-argument
                  directory=True):
    """
    Copy files to a remote host (guest) using the selected client.

    :param client: Type of transfer client
    :param username: Username (if required)
    :param password: Password (if requried)
    :param local_path: Path on the local machine where we are copying from
    :param remote_path: Path on the remote machine where we are copying to
    :param address: Address of remote host(guest)
    :param limit: Speed limit of file transfer.
    :param log_filename: If specified, log all output to this file (SCP only)
    :param log_function: If specified, log all output using this function
    :param verbose: If True, log some stats using logging.debug (RSS only)
    :param timeout: The time duration (in seconds) to wait for the transfer to
            complete.
    :param interface: The interface the neighbours attach to (only use when
                      using ipv6 linklocal address.)
    :param filesize: size of file will be transferred
    :param directory: True to copy recursively if the directory to scp
    :raise: Whatever remote_scp() raises
    """
    if client == "scp":
        scp_to_remote(address, port, username, password, local_path,
                      remote_path, limit, log_filename, log_function, timeout,
                      interface=interface, directory=directory)
    elif client == "rss":
        log_func = None
        if verbose:
            log_func = logging.debug
        if interface:
            address = "%s%%%s" % (address, interface)
        fdclient = rss_client.FileUploadClient(address, port, log_func)
        fdclient.upload(local_path, remote_path, timeout)
        fdclient.close()
    else:
        raise TransferBadClientError(client)


@throughput_transfer
def copy_files_from(address, client, username, password, port, remote_path,
                    local_path, limit="", log_filename=None, log_function=None,
                    verbose=False, timeout=600, interface=None, filesize=None,  # pylint: disable=unused-argument
                    directory=True):
    """
    Copy files from a remote host (guest) using the selected client.

    :param client: Type of transfer client
    :param username: Username (if required)
    :param password: Password (if requried)
    :param remote_path: Path on the remote machine where we are copying from
    :param local_path: Path on the local machine where we are copying to
    :param address: Address of remote host(guest)
    :param limit: Speed limit of file transfer.
    :param log_filename: If specified, log all output to this file (SCP only)
    :param log_function: If specified, log all output using this function
    :param verbose: If True, log some stats using ``logging.debug`` (RSS only)
    :param timeout: The time duration (in seconds) to wait for the transfer to
                    complete.
    :param interface: The interface the neighbours attach to (only
                      use when using ipv6 linklocal address.)
    :param filesize: size of file will be transferred
    :param directory: True to copy recursively if the directory to scp
    :raise: Whatever ``remote_scp()`` raises
    """
    if client == "scp":
        scp_from_remote(address, port, username, password, remote_path,
                        local_path, limit, log_filename, log_function, timeout,
                        interface=interface, directory=directory)
    elif client == "rss":
        log_func = None
        if verbose:
            log_func = logging.debug
        if interface:
            address = "%s%%%s" % (address, interface)
        fdclient = rss_client.FileDownloadClient(address, port, log_func)
        fdclient.download(remote_path, local_path, timeout)
        fdclient.close()
    else:
        raise TransferBadClientError(client)
