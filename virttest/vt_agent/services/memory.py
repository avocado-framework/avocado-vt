import logging

from virttest.vt_utils import memory


LOG = logging.getLogger("avocado.service." + __name__)


def get_usable_memory_size(align=None):
    """
    Sync, then drop host caches, then return host free memory size.

    :param align: MB use to align free memory size
    :return: host free memory size in MB
    """
    LOG.info("Get the usable memory size")
    usable_mem = memory.get_usable_memory_size(align)
    return usable_mem
