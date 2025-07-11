import logging

from virttest.vt_utils import cpu

LOG = logging.getLogger("avocado.service." + __name__)


def get_cpu_vendor_id():
    LOG.info("Getting CPU vendor")
    return cpu.get_cpu_vendor_id()


def get_cpu_model_name():
    LOG.info("Getting CPU model name")
    return cpu.get_cpu_model_name()
