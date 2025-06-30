from .volume import Volume


class BlockVolume(Volume):
    """For disk, lvm, iscsi based volumes"""

    VOLUME_TYPE = "block"
