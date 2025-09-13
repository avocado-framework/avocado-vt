import logging

from ...pool import _ResourcePool
from ...resource import _Resource

LOG = logging.getLogger("avocado." + __name__)


class _IscsiDirectResource(_Resource):
    """
    The iscsi-direct pool resource
    """

    def _initialize(self, config):
        self._lun = config["lun"]


class _IscsiDirectPool(_ResourcePool):
    POOL_TYPE = "iscsi-direct"
