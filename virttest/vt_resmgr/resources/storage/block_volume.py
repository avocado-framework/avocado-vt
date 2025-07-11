import logging

from .volume import _Volume

LOG = logging.getLogger("avocado." + __name__)


class _BlockVolume(_Volume):
    """For disk, lvm, iscsi based volumes"""

    _VOLUME_TYPE = "block"
