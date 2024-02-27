import os
from virttest import utils_io
from ...backing import _ResourceBacking


class _NfsVolumeBacking(_ResourceBacking):

    def __init__(self, config):
        super().__init__(config)
        self._size = config['size']
        self._name = config['name']

    @property
    def allocate(self, pool_connection):
        path = os.path.join(pool_connection.mnt, self._name)
        utils_io.dd(path, self._size)

    def release(self, pool_connection):
        path = os.path.join(pool_connection.mnt, self._name)
        os.unlink(path)

    def info(self, pool_connection):
        path = os.path.join(pool_connection.mnt, self._name)
        s = os.stat(path)
        return {'path': path, 'allocation': s.st_size}


def _get_backing_class(resource_type):
    """
    Get the backing class for a given resource type in case there are
    more than one resources are supported by a nfs pool
    """
    return _NfsVolumeBacking
