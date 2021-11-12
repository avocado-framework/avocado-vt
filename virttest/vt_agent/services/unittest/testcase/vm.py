import logging
import socket

LOG = logging.getLogger("avocado.service." + __name__)


def boot_up():
    hostname = socket.gethostname()
    LOG.info(f"Boot up a guest on the {hostname}")
