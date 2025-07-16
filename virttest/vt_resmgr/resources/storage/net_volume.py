import logging

from .volume import _Volume

LOG = logging.getLogger("avocado." + __name__)


class _NetworkVolume(_Volume):
    """For rbd, iscsi-direct based volumes"""

    _VOLUME_TYPE = "network"
