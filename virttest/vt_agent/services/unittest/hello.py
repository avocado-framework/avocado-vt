import logging
import socket

LOG = logging.getLogger("avocado.service." + __name__)


def say():
    hostname = socket.gethostname()
    LOG.info(f'Say "Hello", from the {hostname}')
