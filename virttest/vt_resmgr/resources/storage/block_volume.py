from .volume import _Volume


class _BlockVolume(_Volume):
    """For disk, lvm, iscsi based volumes"""

    _VOLUME_TYPE = "block"
