from .volume import Volume


class NetworkVolume(Volume):
    """For rbd, iscsi-direct based volumes"""

    VOLUME_TYPE = "network"
