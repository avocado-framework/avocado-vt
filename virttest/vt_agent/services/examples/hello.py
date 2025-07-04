"""
A simple example service that says hello.
Demonstrates a basic service with logging and a return value.
"""

import logging
import socket

LOG = logging.getLogger("avocado.agent." + __name__)


def say_hello(name="World"):
    """
    Greets the caller and returns a message including the server's hostname.

    :param name: The name to include in the greeting.
    :type name: str, optional
    :return: A greeting message.
    :rtype: str
    """
    hostname = socket.gethostname()
    message = f"Hello, {name}! This is vt_agent running on {hostname}."
    LOG.info("Executing say_hello(name='%s'): %s", name, message)
    return message


def ping():
    """
    A simple ping method to check service reachability.

    :return: The string "pong".
    :rtype: str
    """
    LOG.info("Executing ping(): pong")
    return "pong"
