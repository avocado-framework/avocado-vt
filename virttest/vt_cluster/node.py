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
# Copyright: Red Hat Inc. 2022
# Authors: Yongxue Hong <yhong@redhat.com>

"""
Module for providing the interface of node for virt test.
"""

import inspect
import logging
import os

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
    """Generic Node Error."""

    pass


def _remote_login(client, host, port, username, password, prompt, auto_close, timeout):
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
        raise NodeError(e)
    return session


class Node(object):
    """
    Node representation.

    """

    def __init__(self, params, name):
        self._params = params
        self._name = name
        self._host = self.address
        _uri = "http://%s:%s/" % (self._host, self.proxy_port)
        self._uri = None if self.master_node else _uri
        self._agent_server_daemon_pid = None
        self._is_remote_node = not self.master_node
        self._server_daemon_pid_file = None
        self._logger_server = None
        self._session_daemon = None
        self.tag = None

    def __repr__(self):
        return f"<Name: {self._name}; Tag: {self.tag}>"

    @property
    def name(self):
        return self._name

    @property
    def hostname(self):
        return self._params.get("hostname")

    @property
    def address(self):
        return self._params.get("address")

    @property
    def password(self):
        return self._params.get("password")

    @property
    def username(self):
        return self._params.get("username", "root")

    @property
    def proxy_port(self):
        return self._params.get("proxy_port", "8000")

    @property
    def shell_port(self):
        return self._params.get("shell_port", "22")

    @property
    def shell_prompt(self):
        return self._params.get("shell_prompt", "^\[.*\][\#\$]\s*$")

    @property
    def proxy(self):
        return proxy.get_server_proxy(self._uri)

    @property
    def master_node(self):
        return self._params.get("master_node", "no") == "yes"

    @property
    def agent_server_name(self):
        if self._is_remote_node:
            return "server-%s" % self.name

    @property
    def agent_server_dir(self):
        if self._is_remote_node:
            return "/var/run/agent-server/%s" % self.agent_server_name

    @property
    def agent_server_daemon_pid(self):
        if self._is_remote_node:
            return self._agent_server_daemon_pid

    @property
    def logger_server(self):
        if self._is_remote_node:
            return self._logger_server

    def __eq__(self, other):
        if not isinstance(other, Node):
            return False
        return self.address == other.address

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._name)

    def _scp_from_remote(self, source, dest, timeout=600):
        remote.scp_to_remote(
            self._host,
            self.shell_port,
            self.username,
            self.password,
            source,
            dest,
            timeout=timeout,
        )

    def _setup_agent_server_components(self):
        self._scp_from_remote(AGENT_MOD_PATH, self.agent_server_dir)

    def _setup_agent_server_pkgs(self):
        dest_path = os.path.join(self.agent_server_dir, AGENT_MOD)
        for pkg in (avocado, virttest):
            pkg_path = os.path.dirname(inspect.getfile(pkg))
            self._scp_from_remote(pkg_path, dest_path)

        session = self.create_session()
        # FIXME: "pkg_resources.DistributionNotFound"
        target_file = os.path.join(dest_path, "avocado", "__init__.py")
        session.cmd("sed -i 's/initialize_plugins()//g' %s" % target_file)

        # FIXME: fix TypeError: expected str, bytes or os.PathLike object, not tuple
        target_file = os.path.join(dest_path, "virttest", "data_dir.py")
        session.cmd(
            "sed -i 's/persistent_dir != "
            ":/persistent_dir is not None:/g' %s" % target_file
        )

        # FIXME: workaround to install aexpect module
        target_file = os.path.join(dest_path, "aexpect")
        session.cmd_output("rm -rf %s" % target_file, timeout=300)
        cmd = (
            "git clone https://github.com/avocado-framework/aexpect.git %s"
            % target_file
        )
        session.cmd(cmd, timeout=300)
        session.cmd("cd %s && python setup.py develop" % target_file)
        session.close()

    def setup_agent_env(self):
        """Setup the agent environment of node"""
        if self._is_remote_node:
            self.cleanup_agent_env()
            session = self.create_session()
            session.cmd("mkdir -p %s" % self.agent_server_dir)
            session.close()
            self._setup_agent_server_components()
            self._setup_agent_server_pkgs()

    def cleanup_agent_env(self):
        """Cleanup the agent environment of node"""
        if self._is_remote_node:
            agent_session = self.create_session()
            if self.agent_server_dir:
                agent_session.cmd_output("rm -rf %s" % self.agent_server_dir)
                agent_session.close()

    def _start_server_daemon(self, name, host, port, pidfile):
        LOG.info("Starting the server daemon on %s", self.name)
        self._server_daemon_pid_file = pidfile
        self._session_daemon = self.create_session(auto_close=False)
        pythonpath = os.path.join(self.agent_server_dir, AGENT_MOD)
        self._session_daemon.cmd("export PYTHONPATH=%s" % pythonpath)
        self._daemon_cmd = "cd %s &&" % self.agent_server_dir
        self._daemon_cmd += " python3 -m %s" % name
        self._daemon_cmd += " --host=%s" % host
        self._daemon_cmd += " --port=%s" % port
        self._daemon_cmd += " --pid-file=%s" % pidfile
        LOG.info("Sending command line: %s", self._daemon_cmd)
        self._session_daemon.sendline(self._daemon_cmd)

        end_str = "Waiting for connecting."
        timeout = 3
        if not utils_misc.wait_for(
            lambda: (
                end_str in self._session_daemon.get_output() and self.is_server_alive()
            ),
            timeout,
        ):
            err_info = self._session_daemon.get_output()
            LOG.error(
                "Failed to start the server daemon on %s.\n" "The output:\n%s",
                self.name,
                err_info,
            )
            return False
        LOG.info("Start the server daemon successfully on %s.", self.name)
        return True

    def start_agent_server(self):
        """Start the agent server on the node"""
        if self._is_remote_node:
            pidfile = os.path.join(
                self.agent_server_dir, "agent_server_%s.pid" % self.name
            )
            if not self._start_server_daemon(
                name=AGENT_MOD, host=self.address, port=self.proxy_port, pidfile=pidfile
            ):
                raise NodeError("Failed to start agent node daemon on %s" % self.name)

    def stop_agent_server(self):
        """Stop the agent server on the node"""
        if self._is_remote_node:
            if self.is_server_alive():
                try:
                    self.proxy.api.quit()
                except Exception:
                    pass

        if self._session_daemon:
            try:
                self._session_daemon.close()
            except Exception:
                pass

    def upload_agent_log(self, target_path):
        """
        Upload the agent server log to the master node.

        :param target_path: The path of target.
        :type target_path: str
        """
        if self._is_remote_node:
            remote_path = self.proxy.api.get_agent_log_filename()
            remote.scp_from_remote(
                self._host,
                self.shell_port,
                self.username,
                self.password,
                remote_path=remote_path,
                local_path=target_path,
            )

    def upload_service_log(self, target_path):
        """
        Upload the agent service log to the master node.

        :param target_path: The path of target.
        :type target_path: str
        """
        if self._is_remote_node:
            remote_path = self.proxy.api.get_service_log_filename()
            remote.scp_from_remote(
                self._host,
                self.shell_port,
                self.username,
                self.password,
                remote_path=remote_path,
                local_path=target_path,
            )

    def upload_logs(self, target_path):
        """
        Upload the agent service log to the master node.

        :param target_path: The path of target.
        :type target_path: str
        """
        if self._is_remote_node:
            remote_path = os.path.join(self.proxy.api.get_log_dir(), "*")
            remote.scp_from_remote(
                self._host,
                self.shell_port,
                self.username,
                self.password,
                remote_path=remote_path,
                local_path=target_path,
            )

    def create_session(self, auto_close=True, timeout=300):
        """Create a session of the node."""
        session = _remote_login(
            "ssh",
            self._host,
            self.shell_port,
            self.username,
            self.password,
            self.shell_prompt,
            auto_close,
            timeout,
        )
        return session

    def get_server_pid(self):
        """
        Get the PID of the server.

        :return: The PID of the server.
        :type: str
        """
        if self._server_daemon_pid_file:
            _session = self.create_session()
            cmd_open = "cat %s" % self._server_daemon_pid_file
            try:
                pid = _session.cmd_output(cmd_open).strip()
                if pid:
                    self._agent_server_daemon_pid = pid
                return pid
            except Exception as e:
                raise NodeError(e)
            finally:
                _session.close()
        return None

    def is_server_alive(self):
        """
        Check whether the server is alive.

        :return: True if the server is alive otherwise False.
        :rtype: bool
        """
        if not self.get_server_pid():
            return False

        try:
            if not self.proxy.api.is_alive():
                return False
        except Exception as e:
            raise NodeError(e)
        return True
