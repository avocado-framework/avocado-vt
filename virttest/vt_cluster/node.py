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
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>

"""
Module for providing the interface of node for virt test.
"""

import inspect
import logging
import os

import aexpect
import avocado
from aexpect import remote
from aexpect.client import RemoteSession

import virttest
from virttest import utils_misc, vt_agent

from . import ClusterError, proxy

LOG = logging.getLogger("avocado." + __name__)
AGENT_MOD = vt_agent.__name__.split(".")[-1]
AGENT_MOD_PATH = os.path.dirname(vt_agent.__file__)


class NodeError(ClusterError):
    """Exception raised for errors specific to Node operations."""

    pass


def _remote_login(client, host, port, username, password, prompt, auto_close, timeout):
    """
    Establishes an SSH connection to a remote host and handles login prompts.

    This is a helper function for creating remote sessions.

    :param client: The client type (e.g., "ssh").
    :type client: str
    :param host: The hostname or IP address of the remote host.
    :type host: str
    :param port: The SSH port on the remote host.
    :type port: int | str
    :param username: The username for SSH login.
    :type username: str
    :param password: The password for SSH login.
    :type password: str
    :param prompt: The expected shell prompt after successful login.
    :type prompt: str
    :param auto_close: Whether to automatically close the session (not typically used directly here).
    :type auto_close: bool
    :param timeout: Timeout in seconds for the login process.
    :type timeout: int
    :raises NodeError: If login fails or an unexpected error occurs.
    :return: The established RemoteSession object.
    :rtype: aexpect.client.RemoteSession
    """
    cmd = (
        "ssh -o UserKnownHostsFile=/dev/null "
        "-o StrictHostKeyChecking=no -p %s" % port
    )
    cmd += " -o PreferredAuthentications=password"
    cmd += " %s@%s" % (username, host)

    session = RemoteSession(
        cmd,
        linesep="\n",
        prompt=prompt,
        status_test_command="echo $?",
        client=client,
        host=host,
        port=port,
        username=username,
        password=password,
        auto_close=auto_close,
    )
    try:
        remote.handle_prompts(session, username, password, prompt, timeout)
    except Exception as e:
        session.close()
        raise NodeError(
            f"An unexpected error occurred during remote login to "
            f"{host}:{port}: {e}"
        )
    return session


class Node(object):
    """
    Represents a node within the test cluster.

    This class encapsulates the properties and actions related to a single
    node, which can be a remote agent node. It handles agent setup,
    server lifecycle, and log management for remote nodes.

    :param params: A dictionary of parameters for configuring the node.
                   Expected keys include 'address', 'password', 'username',
                   'proxy_port', 'shell_port', 'shell_prompt',
                   'agent_server_base_dir' (optional), 'agent_server_name_tpl'
                   (optional), 'pid_file_tpl' (optional).
    :type params: dict
    :param name: A unique name for this node.
    :type name: str
    """

    def __init__(self, params, name):
        self._params = params
        self._name = name
        self._host = self.address
        self._uri = "http://%s:%s/" % (self._host, self.proxy_port)
        self._agent_server_daemon_pid = None
        self._logger_server = None
        self._session_daemon = None
        self.tag = None

        self._agent_server_base_dir = self._params.get(
            "agent_server_base_dir", "/var/run/agent-server"
        )
        self._agent_server_name_tpl = self._params.get(
            "agent_server_name_tpl", "server-%s"
        )
        self._pid_file_tpl = self._params.get("pid_file_tpl", "agent_server_%s.pid")

    def __repr__(self):
        return (
            f"<Node(Name='{self._name}', Address='{self.address}', Tag='{self.tag}')>"
        )

    @property
    def name(self):
        """The unique name of this node."""
        return self._name

    @property
    def hostname(self):
        """The hostname of this node, if provided in parameters."""
        return self._params.get("hostname")

    @property
    def address(self):
        """The IP address or resolvable name used to connect to this node."""
        return self._params.get("address")

    @property
    def password(self):
        """The password for connecting to this node."""
        return self._params.get("password")

    @property
    def username(self):
        """The username for connecting to this node (defaults to 'root')."""
        return self._params.get("username", "root")

    @property
    def proxy_port(self):
        """The port for the agent server proxy on this node (defaults to '8000')."""
        return self._params.get("proxy_port", "8000")

    @property
    def shell_port(self):
        """The SSH shell port for this node (defaults to '22')."""
        return self._params.get("shell_port", "22")

    @property
    def shell_prompt(self):
        """The expected shell prompt regex for this node."""
        return self._params.get("shell_prompt", "^\[.*\][\#\$]\s*$")

    @property
    def proxy(self):
        """
        Get the server proxy object for communicating with the agent on this node.

        Returns a `_ClientProxy` for remote nodes.
        """
        return proxy.get_server_proxy(self._uri)

    @property
    def agent_server_name(self):
        """The name of the agent server instance on this node (for remote nodes)."""
        return self._agent_server_name_tpl % self.name

    @property
    def agent_server_dir(self):
        """The base directory for the agent server on this node (for remote nodes)."""
        return os.path.join(self._agent_server_base_dir, self.agent_server_name)

    @property
    def _server_daemon_pid_file_path(self):
        """The full path to the agent server's PID file on this node (for remote nodes)."""
        if self.agent_server_dir:
            return os.path.join(self.agent_server_dir, self._pid_file_tpl % self.name)

    @property
    def agent_server_daemon_pid(self):
        """The PID of the agent server daemon, if running and read (for remote nodes)."""
        return self._agent_server_daemon_pid

    @property
    def logger_server(self):
        """The logger server associated with this node (intended for remote nodes)."""
        return self._logger_server

    def __eq__(self, other):
        if not isinstance(other, Node):
            return False
        return self.address == other.address

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._name)

    def _scp_to_remote(self, source, dest, timeout=600):
        try:
            remote.scp_to_remote(
                self._host,
                self.shell_port,
                self.username,
                self.password,
                source,
                dest,
                timeout=timeout,
            )
        except Exception as e:
            raise NodeError(f"SCP failed: {e}") from e

    def _create_session(self, timeout=300):
        """
        Create and return a new remote SSH session to this node.

        :param timeout: Timeout in seconds for establishing the session.
                        Defaults to 300.
        :type timeout: int
        :return: An established `aexpect.client.RemoteSession` object.
        :rtype: aexpect.client.RemoteSession
        :raises NodeError: If session creation fails.
        """
        session = _remote_login(
            "ssh",
            self._host,
            self.shell_port,
            self.username,
            self.password,
            self.shell_prompt,
            True,
            timeout,
        )
        return session

    def _get_server_pid(self):
        """
        Read and return the agent server's PID from its PID file on the remote node.

        :return: The PID string if found, otherwise None.
        :rtype: str | None
        :raises NodeError: If reading the PID file fails.
        """
        pid_file_path = self._server_daemon_pid_file_path
        if pid_file_path:
            _session = self._create_session()
            cmd_open = "cat %s" % pid_file_path
            try:
                pid = _session.cmd_output(cmd_open).strip()
                if pid:
                    self._agent_server_daemon_pid = pid
                return pid
            except Exception as e:
                raise NodeError(
                    f"Failed get the agent server daemon pid "
                    f"with {pid_file_path}: {e}"
                )
            finally:
                _session.close()
        return None

    def _is_server_alive(self):
        """
        Check if the agent server on the remote node is alive.

        This is determined by checking if a PID can be read from the PID file
        and if the server's proxy API reports it's alive.

        :return: True if the server is considered alive, False otherwise.
        :rtype: bool
        """
        if not self._get_server_pid():
            return False

        try:
            if not self.proxy.api.is_alive():
                return False
        except Exception as e:
            LOG.warning(
                "Node %s: Error checking proxy API is_alive(): %s", self.name, e
            )
            return False
        return True

    def _setup_agent_server_components(self):
        """
        Copy essential agent server components to the remote node.

        Specifically, copies the agent module itself (defined by `AGENT_MOD_PATH`)
        to the `agent_server_dir` on the remote node.
        """
        self._scp_to_remote(AGENT_MOD_PATH, self.agent_server_dir)

    def _setup_agent_server_pkgs(self):
        """
        Set up necessary Python packages on the remote agent node.

        This involves:
        1. Copying ``avocado`` and ``virttest`` package sources to the agent.
        2. Patching ``avocado/__init__.py`` to prevent plugin initialization.
        3. Patching ``virttest/data_dir.py`` to fix a type error.
        4. Copying ``aexpect`` source to the agent and installing it in
           develop mode.
        """
        dest_path = os.path.join(self.agent_server_dir, AGENT_MOD)

        for pkg in (avocado, virttest):
            pkg_path = os.path.dirname(inspect.getfile(pkg))
            self._scp_to_remote(pkg_path, dest_path)

        session = self._create_session()
        try:
            # FIXME: Using sed to patch code is highly fragile. This disables
            #  plugin initialization to avoid errors when avocado is used as a
            #  library. A better approach would be to use an avocado API or
            #  configuration option if one exists.
            target_file = os.path.join(dest_path, "avocado", "__init__.py")
            session.cmd("sed -i 's/initialize_plugins()//g' %s" % target_file)

            # FIXME: This sed command patches a bug in the copied source.
            #  The bug should be fixed in the virttest library itself.
            target_file = os.path.join(dest_path, "virttest", "data_dir.py")
            session.cmd(
                "sed -i 's/persistent_dir != "
                ":/persistent_dir is not None:/g' %s" % target_file
            )

            target_file = os.path.join(dest_path, "aexpect")
            session.cmd_output("rm -rf %s" % target_file, timeout=300)
            aexpect_source_file = os.path.dirname(
                os.path.dirname(inspect.getsourcefile(aexpect))
            )
            self._scp_to_remote(aexpect_source_file, target_file)
            session.cmd("cd %s && python3 setup.py develop" % target_file)
        finally:
            session.close()

    def setup_agent_env(self):
        """
        Set up the agent environment on a remote node.

        This involves cleaning up any previous environment, creating necessary
        directories, and setting up server components and packages.
        """
        self.cleanup_agent_env()
        session = self._create_session()
        try:
            session.cmd("mkdir -p %s" % self.agent_server_dir)
        finally:
            session.close()
        self._setup_agent_server_components()
        self._setup_agent_server_pkgs()

    def cleanup_agent_env(self):
        """
        Clean up the agent environment on a remote node.

        This typically involves removing the agent server directory.
        """
        if self.agent_server_dir:
            agent_session = self._create_session()
            try:
                agent_session.cmd_output("rm -rf %s" % self.agent_server_dir)
            finally:
                agent_session.close()

    def _start_server_daemon(self, name, host, port):
        """
        Start a server daemon process on the remote node.

        :param name: The module name of the daemon to start (e.g., 'vt_agent.server').
        :type name: str
        :param host: The host address the daemon should bind to.
        :type host: str
        :param port: The port number the daemon should bind to.
        :type port: int | str
        :return: True if the daemon started successfully, False otherwise.
        :rtype: bool
        """
        pid_file_path = self._server_daemon_pid_file_path
        if not pid_file_path:
            return False

        self._session_daemon = self._create_session()
        pythonpath = os.path.join(self.agent_server_dir, AGENT_MOD)
        self._session_daemon.cmd("export PYTHONPATH=%s" % pythonpath)
        self._daemon_cmd = "cd %s &&" % self.agent_server_dir
        self._daemon_cmd += " python3 -m %s" % name
        self._daemon_cmd += " --host=%s" % host
        self._daemon_cmd += " --port=%s" % port
        self._daemon_cmd += " --pid-file=%s" % pid_file_path
        LOG.info(
            "Node %s: Sending command line for daemon %s: %s",
            self.name,
            name,
            self._daemon_cmd,
        )
        self._session_daemon.sendline(self._daemon_cmd)

        end_str = "Waiting for connecting."
        timeout = 3
        if not utils_misc.wait_for(
            lambda: (
                end_str in self._session_daemon.get_output() and self._is_server_alive()
            ),
            timeout,
        ):
            err_info = self._session_daemon.get_output()
            LOG.error(
                "Failed to start the server daemon %s on node %s.\n"
                "Output from daemon session:\n%s",
                name,
                self.name,
                err_info,
            )
            return False
        LOG.info("Successfully started server daemon %s on node %s.", name, self.name)
        return True

    def start_agent_server(self):
        """
        Start the agent server on this node if it's a remote node.

        This involves starting the server daemon and copying necessary
        configuration files like the QEMU command-line format JSON.
        Does nothing if the node is a master node.

        :raises NodeError: If starting the agent server fails or if PID path is not configured.
        """
        if not self._server_daemon_pid_file_path:
            raise NodeError("PID file path is not configured for node %s." % self.name)

        if not self._start_server_daemon(
            name=AGENT_MOD, host=self.address, port=self.proxy_port
        ):
            raise NodeError("Failed to start agent node daemon on %s" % self.name)

    def stop_agent_server(self):
        """
        Stop the agent server on this node if it's a remote node.

        Attempts to gracefully shut down the server via its proxy API.
        Also ensures the daemon session is closed.
        """
        if self._is_server_alive():
            try:
                self.proxy.api.quit()
            except Exception:
                pass

        if self._session_daemon:
            try:
                self._session_daemon.close()
            except Exception:
                pass

    def _upload_files(self, remote_path, target_path):
        """
        Upload files from a remote path on this node to a local target path on the master.

        This method is used internally for log collection. It also attempts to
        trigger a cleanup of the temporary files on the remote node after uploading.

        :param remote_path: The source path on the remote agent node (can include wildcards).
        :type remote_path: str
        :param target_path: The destination path on the master node.
        :type target_path: str
        """
        try:
            remote.scp_from_remote(
                self._host,
                self.shell_port,
                self.username,
                self.password,
                remote_path=remote_path,
                local_path=target_path,
            )
        except Exception as e:
            LOG.warning(
                f"Node {self.name}: Failed to upload {remote_path} to {target_path}: {e}"
            )
        finally:
            # FIXME: Clean up the log files to avoid copying them to the next one
            # TODO: To mark an case ID or case name for the log files
            try:
                self.proxy.api.cleanup_tmp_files(remote_path)
            except Exception as e:
                LOG.warning(
                    "Node %s: Failed to clean up remote files at %s: %s",
                    self.name,
                    remote_path,
                    e,
                )

    def upload_agent_log(self, target_path):
        """
        Upload the main agent server log file from the remote node to the specified local path.

        :param target_path: The local directory or file path to upload the log to.
        :type target_path: str
        """
        try:
            remote_path = self.proxy.api.get_agent_log_filename()
            if remote_path:
                self._upload_files(remote_path, target_path)
        except Exception as e:
            LOG.warning("Node %s: Failed to upload agent log: %s", self.name, e)

    def upload_service_log(self, target_path):
        """
        Upload the agent's service-specific log file(s) from the remote node.

        :param target_path: The local directory or file path to upload logs to.
        :type target_path: str
        """
        try:
            remote_path = self.proxy.api.get_service_log_filename()
            if remote_path:
                self._upload_files(remote_path, target_path)
        except Exception as e:
            LOG.warning("Node %s: Failed to upload service log: %s", self.name, e)

    def upload_logs(self, target_path):
        """
        Upload all relevant agent and service logs from this node to the master.

        :param target_path: The path of target.
        :type target_path: str
        """
        self.upload_service_log(target_path)
