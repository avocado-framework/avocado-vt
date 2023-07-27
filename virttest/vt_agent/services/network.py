import socket
import logging

from avocado.utils.network import ports
from virttest import utils_vsock

LOG = logging.getLogger("avocado.service." + __name__)


def find_free_ports(start_port, end_port, count, address="localhost",
                    sequent=False, family=socket.AF_INET,
                    protocol=socket.SOCK_STREAM,):
    """
    Find free ports in the specified range.

    :param start_port: start port
    :param end_port: end port
    """
    LOG.debug("Finding the free ports in the specified range")
    return ports.find_free_ports(start_port, end_port, count,
                                address, sequent, family, protocol)


def get_free_cid(start_cid):
    """
    Get free cid in the specified range

    :param start_cid: int
    :return: free cid
    """
    LOG.debug("Getting the free cid in the specified range")
    return utils_vsock.get_guest_cid(start_cid)
