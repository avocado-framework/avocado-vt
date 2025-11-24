"""
A simple example service that says hello.
Demonstrates a basic service with logging and a return value.
"""

import logging
import socket

# pylint: disable=E0611
from avocado_vt.agent.core.logger import DEFAULT_LOG_NAME

LOG = logging.getLogger(f"{DEFAULT_LOG_NAME}." + __name__)


def ping():
    """
    A simple ping method to check service reachability.

    :return: The string "pong".
    :rtype: str
    """
    hostname = socket.gethostname()
    LOG.info(f"{hostname}: Executing ping")
    return f"Pong from {hostname}"
