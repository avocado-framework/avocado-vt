import os

import utils_disk

from avocado.utils.path import init_dir

from ...pool_connection import _ResourcePoolAccess
from ...pool_connection import _ResourcePoolConnection


class _NfsPoolAccess(_ResourcePoolAccess):
    """
    Mount options
    """

    def __init__(self, pool_access_config):
        self._options = pool_access_config["nfs_options"]

    def __str__(self):
        return self._options


class _NfsPoolConnection(_ResourcePoolConnection):
    _CONNECT_POOL_TYPE = "nfs"

    def __init__(self, pool_config):
        super().__init__(pool_params)
        self._connected_pool = pool_params["pool_id"]
        self._nfs_server = pool_params["nfs_server"]
        self._export_dir = pool_params["nfs_export_dir"]
        self._nfs_access = _NfsPoolAccess(pool_params["access"])
        self._mnt = pool_params["nfs_mnt_dir"]
        self._create_mnt = not os.path.exists(self.mnt)

    def startup(self):
        src = "{host}:{export}".format(self._nfs_server, self._export_dir)
        dst = self.mnt
        if self._create_mnt:
            init_dir(dst)
        options = str(self._nfs_access)
        utils_disk.mount(src, dst, fstype="nfs", options=options)

    def shutdown(self):
        src = "{host}:{export}".format(self._nfs_server, self._export_dir)
        dst = self._mnt
        utils_disk.umount(src, dst, fstype="nfs")
        if self._create_mnt:
            os.removedirs(self.mnt)

    def connected(self):
        src = "{host}:{export}".format(self._nfs_server, self._export_dir)
        dst = self.mnt
        return utils_disk.is_mount(src, dst, fstype="nfs")

    @property
    def mnt(self):
        return self._mnt

    @property
    def info(self):
        return dict()
