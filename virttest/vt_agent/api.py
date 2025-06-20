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
import logging.handlers
import os
import shutil
import signal

from .core import data_dir
from .core.logger import LOG_FORMAT

LOG = logging.getLogger("avocado.agent." + __name__)


def quit():
    """Quit the agent server."""
    pid = os.getpid()
    LOG.info("Quit the server daemon(PID:%s).", pid)
    os.kill(pid, signal.SIGKILL)


def is_alive():
    """Check whether the agent server is alive."""
    LOG.info("The server daemon is alive.")
    return True


def start_logger_client(host, port):
    """Start the agent logger client"""
    try:
        os.remove(data_dir.SERVICE_LOG_FILENAME)
    except FileNotFoundError:
        pass

    logger = logging.getLogger("avocado.service")
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(filename=data_dir.SERVICE_LOG_FILENAME)
    file_handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
    logger.addHandler(file_handler)

    virttest_logger = logging.getLogger("avocado.virttest")
    virttest_logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(filename=data_dir.SERVICE_LOG_FILENAME)
    file_handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
    virttest_logger.addHandler(file_handler)

    LOG.info("Start the logger client.")
    socket_handler = logging.handlers.SocketHandler(host, port)
    socket_handler.setLevel(logging.DEBUG)
    logger.addHandler(socket_handler)
    virttest_logger.addHandler(socket_handler)


def stop_logger_client():
    """Stop the agent logger client."""
    LOG.info("Stop the logger client.")
    for handler in logging.getLogger("avocado.service").handlers:
        handler.close()
    logging.getLogger("avocado.service").handlers.clear()


def get_agent_log_filename():
    """Get the filename of the agent log."""
    return data_dir.AGENT_LOG_FILENAME


def get_service_log_filename():
    """Get the filename of the service log."""
    return data_dir.SERVICE_LOG_FILENAME


def get_log_dir():
    """Get the filename of the logs."""
    return data_dir.get_log_dir()


def get_console_log_dir():
    """Get the filename of the console logs."""
    return data_dir.get_console_log_dir()


def get_daemon_log_dir():
    """Get the filename of the daemon logs."""
    return data_dir.get_daemon_log_dir()


def get_ip_sniffer_log_dir():
    """Get the filename of the ip sniffer logs."""
    return data_dir.get_ip_sniffer_log_dir()


def cleanup_tmp_files(file_path):
    """
    Cleanup temporary files
    """
    try:
        if os.path.isdir(file_path):
            shutil.rmtree(file_path)
        elif os.path.isfile(file_path):
            os.remove(file_path)
        else:
            files = glob.glob(file_path)
            for file in files:
                if os.path.isfile(file):
                    os.remove(file)
                else:
                    shutil.rmtree(file)
    except (FileNotFoundError, OSError):
        pass
