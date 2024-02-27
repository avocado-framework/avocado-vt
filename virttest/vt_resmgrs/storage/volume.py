from ..resource import _Resource


class _Volume(_Resource):
    """
    Storage volumes are abstractions of physical partitions,
    LVM logical volumes, file-based disk images
    """

    _RESOURCE_TYPE = 'volume'
    _VOLUME_TYPE = None

    @property
    def volume_type(cls):
        return cls._VOLUME_TYPE


class _FileVolume(_Volume):
    """For file based volumes"""

    _VOLUME_TYPE = 'file'

    def __init__(self, config):
        self._path = None
        self._capacity = 0
        self._allocation = 0
        super().__init__(config)


class _BlockVolume(_Volume):
    """For disk, lvm, iscsi based volumes"""

    _VOLUME_TYPE = 'block'

    def __init__(self, config):
        self._path = None
        self._capacity = 0
        self._allocation = 0
        super().__init__(config)


class _NetworkVolume(_Volume):
    """For rbd, iscsi-direct based volumes"""

    _VOLUME_TYPE = 'network'
