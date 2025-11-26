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

import glob
import logging
import os
import shutil
import signal
import sys

# pylint: disable=E0611
from avocado_vt.agent.core import data_dir, rpc
from avocado_vt.agent.core.logger import DEFAULT_LOG_NAME

LOG = logging.getLogger(f"{DEFAULT_LOG_NAME}." + __name__)


def _signal_handler(signum, frame):
    """
    Handle shutdown signals gracefully.

    :param signum: Signal number
    :type signum: int
    :param frame: Current stack frame
    :type frame: frame
    """
    signal_names = {signal.SIGTERM: "SIGTERM", signal.SIGINT: "SIGINT"}
    signal_name = signal_names.get(signum, f"Signal {signum}")
    LOG.info("Received %s, daemon graceful shutdown...", signal_name)
    sys.exit(0)


def _validate_server_params(host, port, pid_file):
    """
    Validate server parameters before starting.

    :param host: The host address
    :type host: str
    :param port: The port number
    :type port: int
    :param pid_file: The PID file path
    :type pid_file: str
    :raises ValueError: If parameters are invalid
    """
    if not host:
        raise ValueError("Host address cannot be empty")

    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ValueError(f"Invalid port number: {port}")

    if not pid_file:
        raise ValueError("PID file path cannot be empty")


def _write_pid_file(pid_file):
    """
    Write the current process ID to the PID file.

    :param pid_file: Path to the PID file
    :type pid_file: str
    :raises OSError: If PID file cannot be written
    """
    pid = str(os.getpid())
    try:
        with open(pid_file, "w") as f:
            f.write(pid + "\n")
    except OSError as e:
        LOG.error("Failed to write PID file %s: %s", pid_file, e)
        raise


def _cleanup_pid_file(pid_file):
    """
    Clean up the PID file on shutdown.

    :param pid_file: Path to the PID file
    :type pid_file: str
    """
    if os.path.exists(pid_file):
        try:
            os.remove(pid_file)
        except OSError as e:
            LOG.warning("Failed to remove PID file %s: %s", pid_file, e)


def _cleanup_tmp_dirs():
    """
    Cleans up temporary directories created by get_tmp_dir().

    It looks for items prefixed with "agent_tmp_" inside the main data
    directory and attempts to remove them.
    """
    data_dir_path = data_dir.get_data_dir()
    if not os.path.isdir(data_dir_path):
        return

    tmp_pattern = os.path.join(data_dir_path, "agent_tmp_*")
    tmp_dirs = glob.glob(tmp_pattern)

    if not tmp_dirs:
        return

    for tmp_dir in tmp_dirs:
        if os.path.isdir(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
            except OSError as e:
                LOG.warning("Failed to remove temporary directory %s: %s", tmp_dir, e)


def run(host, port, pid_file):
    """
    Run the agent server daemon.

    This function initializes the RPC server, loads services, writes the PID file,
    and starts serving requests. It handles graceful shutdown on interruption.

    :param host: The host address for the agent server to bind to
    :type host: str
    :param port: The port number for the agent server to listen on
    :type port: int
    :param pid_file: Path to write the process ID file
    :type pid_file: str
    :raises ValueError: If parameters are invalid
    :raises SystemExit: On startup failure or shutdown
    """
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    try:
        _validate_server_params(host, port, pid_file)

        pid = str(os.getpid())
        LOG.info("Agent daemon starting with PID %s", pid)

        services = rpc.service.load_services()

        server = rpc.server.RPCServer((host, port))
        server.register_services(services)

        _write_pid_file(pid_file)

        server.serve_forever()

    except KeyboardInterrupt:
        LOG.info("Keyboard interrupt received, shutting down gracefully")

    except OSError as e:
        if "Address already in use" in str(e):
            LOG.error(
                "Cannot start server: Address %s:%s is already in use", host, port
            )
            LOG.error("Another agent instance may already be running")
        else:
            LOG.error("OS error during server operation: %s", e)
        sys.exit(1)

    except ValueError as e:
        LOG.error("Configuration error: %s", e)
        sys.exit(1)

    except Exception as e:
        LOG.error("Unexpected error during server operation: %s", e, exc_info=True)
        sys.exit(1)

    finally:
        _cleanup_pid_file(pid_file)
        _cleanup_tmp_dirs()
