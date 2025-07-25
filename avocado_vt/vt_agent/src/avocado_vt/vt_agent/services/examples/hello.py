"""
A simple example service that says hello.
Demonstrates a basic service with logging and a return value.
"""

import logging
import socket

LOG = logging.getLogger("avocado.service." + __name__)


def ping():
    """
    A simple ping method to check service reachability.

    :return: The string "pong".
    :rtype: str
    """
    hostname = socket.gethostname()
    LOG.info(f"{hostname}: Executing ping")
    return f"pong from {hostname}"
