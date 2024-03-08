import os
from virttest import utils_io
from ...backing import _ResourceBacking


class _NfsVolumeBacking(_ResourceBacking):
    _SOURCE_POOL_TYPE = "nfs"
    _BINDING_RESOURCE_TYPE = "volume"

    def __init__(self, config):
        super().__init__(config)
        self._allocation = 0
        self._handlers.update({
            "resize": self.resize_volume,
        })

    def allocate_resource(self, pool_connection, arguments):
        path = os.path.join(pool_connection.mnt, self._name)
        utils_io.dd(path, self._size)

    def release_resource(self, pool_connection, arguments):
        path = os.path.join(pool_connection.mnt, self._name)
        os.unlink(path)

    def resize_volume(self, pool_connection, arguments):
        pass

    def info_resource(self, pool_connection, verbose=False):
        info = {
            "spec": {
                "path": os.path.join(pool_connection.mnt, self._filename),
            }
        }

        if verbose:
            s = os.stat(path)
            info["spec"].update({"allocation": s.st_size})

        return info


def _get_backing_class(resource_type):
    """
    Get the backing class for a given resource type in case there are
    more than one resources are supported by a nfs pool
    """
    return _NfsVolumeBacking
