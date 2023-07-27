import logging

from vt_agent.core import data_dir

LOG = logging.getLogger("avocado.service." + __name__)


def get_data_dir():
    return data_dir.get_data_dir()
