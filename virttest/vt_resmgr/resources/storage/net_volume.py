from .volume import _Volume


class _NetworkVolume(_Volume):
    """For rbd, iscsi-direct based volumes"""

    _VOLUME_TYPE = "network"
