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

import logging.handlers
import os
import signal


from . import AGENT_LOG_FILENAME
from . import SERVICE_LOG_FILENAME
from . import LOG_FORMAT

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
        os.remove(SERVICE_LOG_FILENAME)
    except FileNotFoundError:
        pass

    logger = logging.getLogger("avocado.service")
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(filename=SERVICE_LOG_FILENAME)
    file_handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
    logger.addHandler(file_handler)

    LOG.info("Start the logger client.")
    socket_handler = logging.handlers.SocketHandler(host, port)
    socket_handler.setLevel(logging.DEBUG)
    logger.addHandler(socket_handler)


def stop_logger_client():
    """Stop the agent logger client."""
    LOG.info("Stop the logger client.")
    for handler in logging.getLogger("avocado.service").handlers:
        handler.close()
    logging.getLogger("avocado.service").handlers.clear()


def get_agent_log_filename():
    """Get the filename of the agent log."""
    return AGENT_LOG_FILENAME


def get_service_log_filename():
    """Get the filename of the service log."""
    return SERVICE_LOG_FILENAME
