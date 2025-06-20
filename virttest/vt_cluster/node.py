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
Node management module for virtual test cluster environments.

This module provides the Node class and related utilities for managing
individual nodes within a virtualization test cluster. It handles:

- Remote SSH connections and session management
- Agent server setup and lifecycle management
- File transfer operations to remote nodes
- Package deployment and environment setup
- Proxy communication for distributed test execution

Key components:
- Node: Main class representing a cluster node with agent capabilities
- NodeError: Exception class for node-specific errors

The module is designed to work with the remote nodes, with special handling
for remote agent deployment and management.
"""

import inspect
import logging
import os

import virttest
from virttest import utils_misc, data_dir
# from virttest import vt_agent
import avocado_vt

import aexpect
import avocado
from aexpect import remote
from aexpect.client import RemoteSession

from . import ClusterError, proxy

LOG = logging.getLogger("avocado." + __name__)
# AGENT_MOD = vt_agent.__name__.split(".")[-1]
# AGENT_MOD_PATH = os.path.dirname(vt_agent.__file__)
# AGENT_MOD = "vt_agent"
# AGENT_MOD_PATH = os.path.join(os.path.dirname(avocado_vt.__file__), "vt_agent")


class NodeError(ClusterError):
    """Exception raised for errors specific to Node operations."""

    pass


class Node(object):
    """
    Represents a node within the test cluster.

    This class encapsulates the properties and actions related to a single
    node, which can be a remote agent node. It handles agent setup and its lifecycle.

    :param params: A dictionary of parameters for configuring the node.
                   Expected keys include 'address', 'hostname', 'password',
                   'username', 'proxy_port', 'shell_port', 'shell_prompt',
                   'agent_base_dir'.
    :type params: dict
    :param name: A unique name for this node.
    :type name: str
    """

    def __init__(self, params, name):
        self._config = params

        self._name = name
        self._address = self._config.get("address")
        self._hostname = self._config.get("hostname")
        self._host = self._address if self._address else self._hostname

        self._password = self._config.get("password", "root")
        self._username = self._config.get("username", "root")
        self._shell_port = self._config.get("shell_port", "22")
        self._shell_prompt = self._config.get("shell_prompt", "^\[.*\][\#\$]\s*$")

        self._proxy_port = self._config.get("proxy_port", "9999")
        self._uri = "http://%s:%s/" % (self._host, self._proxy_port)
        self._proxy = proxy.get_server_proxy(self._uri)
        self._agent_pid = None
        self.tag = None

        self._agent_base_dir = self._config.get(
            "agent_base_dir", "/var/run/vt_agent_server"
        )
        self._agent_dir = os.path.join(self._agent_base_dir, f"{name}")
        self._agent_pid_filename = os.path.join(self._agent_dir, "vt_agent.pid")

    def __repr__(self):
        return f"<Node(Name='{self._name}', Host='{self._host}', Tag='{self.tag}')>"

    @property
    def name(self):
        """The unique name of this node."""
        return self._name

    @property
    def host(self):
        """
        The host address or hostname of this node.

        :return: The host address (IP) or hostname used to connect to this node.
        :rtype: str
        """
        return self._host

    @property
    def proxy(self):
        """
        Get the server proxy object for communicating with the agent on this node.

        Returns a `_ClientProxy` for remote nodes.
        """
        return self._proxy

    def __eq__(self, other):
        """
        Check equality between two Node instances based on their address.

        :param other: Another object to compare with.
        :type other: object
        :return: True if both nodes have the same address, False otherwise.
        :rtype: bool
        """
        if not isinstance(other, Node):
            return False
        return self._address == other._address

    def __ne__(self, other):
        """
        Check inequality between two Node instances.

        :param other: Another object to compare with.
        :type other: object
        :return: True if nodes are not equal, False if they are equal.
        :rtype: bool
        """
        return not self.__eq__(other)

    def __hash__(self):
        """
        Return hash value for the Node instance based on its name.

        This allows Node instances to be used in sets and as dictionary keys.

        :return: Hash value of the node name.
        :rtype: int
        """
        return hash(self._name)

    def _scp_to_remote(self, source, dest, timeout=600):
        """
        Copy files or directories to the remote node using SCP.

        :param source: Local source file or directory path to copy.
        :type source: str
        :param dest: Remote destination path where files will be copied.
        :type dest: str
        :param timeout: Timeout in seconds for the SCP operation. Defaults to 600.
        :type timeout: int
        :raises NodeError: If the SCP operation fails.
        """
        try:
            remote.scp_to_remote(
                self._host,
                self._shell_port,
                self._username,
                self._password,
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
        cmd = (
            "ssh -o UserKnownHostsFile=/dev/null "
            "-o StrictHostKeyChecking=no -p %s" % self._shell_port
        )
        cmd += " -o PreferredAuthentications=password"
        cmd += " %s@%s" % (self._username, self._host)

        session = RemoteSession(
            cmd,
            linesep="\n",
            prompt=self._shell_prompt,
            status_test_command="echo $?",
            client="ssh",
            host=self._host,
            port=self._shell_port,
            username=self._username,
            password=self._password,
        )
        try:
            remote.handle_prompts(
                session, self._username, self._password, self._shell_prompt, timeout
            )
        except Exception as e:
            session.close()
            raise NodeError(
                f"An unexpected error occurred during remote login to "
                f"{self._host}:{self._shell_port}: {e}"
            )
        return session

    def _get_agent_pid(self):
        """
        Read and return the agent daemon's PID from its PID file on the remote node.

        :return: The PID string if found, otherwise None.
        :rtype: str | None
        :raises NodeError: If reading the PID file fails.
        """
        if self._agent_pid_filename:
            _session = self._create_session()
            cmd_open = "cat %s" % self._agent_pid_filename
            try:
                pid = _session.cmd_output(cmd_open).strip()
                if pid:
                    self._agent_pid = pid
                return pid
            except Exception as e:
                raise NodeError(
                    f"Failed get the agent daemon pid "
                    f"with {self._agent_pid_filename}: {e}"
                )
            finally:
                _session.close()
        return None

    def _is_agent_alive(self):
        """
        Check if the agent server on the remote node is alive.

        This is determined by checking if a PID can be read from the PID file
        and if the server's proxy API reports it's alive.

        :return: True if the server is considered alive, False otherwise.
        :rtype: bool
        """
        if not self._get_agent_pid():
            return False

        try:
            # if not self.proxy.api.is_alive()
            if not self.proxy.core.is_alive():
                return False
        except Exception as e:
            LOG.warning(
                "Node %s: Error checking proxy API is_alive(): %s", self.name, e
            )
            return False
        return True

    def _setup_agent_pkgs(self):
        """
        Set up necessary Python packages on the remote agent node.

        This involves:
        1. Copying ``avocado`` and ``virttest`` package sources to the agent.
        2. Patching ``avocado/__init__.py`` to prevent plugin initialization.
        3. Patching ``virttest/data_dir.py`` to fix a type error.
        4. Copying ``aexpect`` source to the agent and installing it in
           develop mode.
        """
        # agent_pkg_path = os.path.dirname(vt_agent.__file__)
        agent_pkg_path = os.path.join(os.path.dirname(avocado_vt.__file__),
                                      "vt_agent")
        self._scp_to_remote(agent_pkg_path, self._agent_dir)

        dest_path = os.path.join(self._agent_dir, "vt_agent")

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

            # Install the vt_agent by pip install
            out = session.cmd("pip3 install -e %s" % os.path.join(self._agent_dir, "vt_agent"))
            LOG.debug(f"Output of installation avocado_vt.agent: {out}")

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
            session.cmd("mkdir -p %s" % self._agent_dir)
        finally:
            session.close()
        self._setup_agent_pkgs()

    def cleanup_agent_env(self):
        """
        Clean up the agent environment on a remote node.

        This typically involves removing the agent server directory.
        """
        if self._agent_dir:
            agent_session = self._create_session()
            try:
                out = agent_session.cmd_output("pip3 uninstall -y avocado_vt.agent")
                LOG.debug(f"Output of uninstallation avocado_vt.agent: {out}")
                agent_session.cmd_output("rm -rf %s" % self._agent_dir)
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
        self._session_daemon = self._create_session()
        pythonpath = os.path.join(self._agent_dir, "vt_agent")
        # self._session_daemon.cmd("export PYTHONPATH=%s" % pythonpath)
        self._daemon_cmd = "export PYTHONPATH=%s &&" % pythonpath
        self._daemon_cmd += "cd %s &&" % self._agent_dir
        self._daemon_cmd += " python3 -m %s" % name
        # self._daemon_cmd = " python3 -m %s" % name
        self._daemon_cmd += " --host=%s" % host
        self._daemon_cmd += " --port=%s" % port
        self._daemon_cmd += " --pid-file=%s" % self._agent_pid_filename
        LOG.info(
            "Node %s: Sending command line for daemon %s: %s",
            self.name,
            name,
            self._daemon_cmd,
        )
        self._session_daemon.sendline(self._daemon_cmd)

        # end_str = "Waiting for connecting."
        end_str = "Agent daemon starting with PID"
        timeout = 3
        if not utils_misc.wait_for(
            lambda: (
                end_str in self._session_daemon.get_output() and self._is_agent_alive()
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

    # FIXME: Copy the qemu cmdline format json file here,
    #  it should be covered by the internal tools
    def _copy_qemu_cmdline_format_json(self):
        """
        Copy the QEMU command-line format JSON file to the agent node.

        This is a workaround and should ideally be handled by internal tools.
        The file is copied from the local backend configuration to the agent's
        data directory.
        """
        dst_path = self.proxy.data_dir.get_data_dir()
        src_path = data_dir.get_backend_cfg_path("qemu", "qemu_cmdline_format")
        if os.path.exists(src_path):
            self._scp_to_remote(src_path, dst_path)

    def start_agent_server(self):
        """
        Start the agent server on this node if it's a remote node.

        This involves starting the server daemon and copying necessary
        configuration files like the QEMU command-line format JSON.
        Does nothing if the node is a controller node.

        :raises NodeError: If starting the agent server fails
        """
        # if not self._start_server_daemon(
        #     name="vt_agent", host=self._host, port=self._proxy_port
        # ):
        if not self._start_server_daemon(
            name="avocado_vt.agent", host=self._host, port=self._proxy_port
        ):
            raise NodeError("Failed to start agent node daemon on %s" % self.name)
        self._copy_qemu_cmdline_format_json()

    def stop_agent_server(self):
        """
        Stop the agent server on this node if it's a remote node.

        Attempts to gracefully shut down the server via its proxy API.
        Also ensures the daemon session is closed.
        """
        if self._is_agent_alive():
            try:
                # self.proxy.api.quit()
                self.proxy.core.quit()
            except Exception:
                pass

        if self._session_daemon:
            try:
                self._session_daemon.close()
            except Exception:
                pass

    def copy_files_from(self, local_path, remote_path):
        """Copy files from remote host to local path.

        :param local_path: Local destination path
        :param remote_path: Remote source path
        """
        try:
            remote.scp_from_remote(
                self._host,
                self._shell_port,
                self._username,
                self._password,
                remote_path,
                local_path,
            )
        except Exception as e:
            LOG.error(f"SCP failed: {e}")
