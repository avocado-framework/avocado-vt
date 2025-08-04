import logging

from virttest import arch

LOG = logging.getLogger("avocado.service." + __name__)


def get_arch():
    LOG.info("Getting the architecture")
    return arch.ARCH
