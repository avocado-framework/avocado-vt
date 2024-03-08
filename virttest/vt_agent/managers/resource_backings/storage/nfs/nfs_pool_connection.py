import logging

from avocado.utils.path import init_dir

from virttest import utils_misc

from ...pool_connection import _ResourcePoolAccess, _ResourcePoolConnection

LOG = logging.getLogger("avocado.service." + __name__)


class _NfsPoolAccess(_ResourcePoolAccess):
    """
    Mount options
    """

    def __init__(self, pool_access_config):
        self._options = pool_access_config.get("mount-options", "")

    def __str__(self):
        return self._options if self._options else ""


class _NfsPoolConnection(_ResourcePoolConnection):
    _CONNECT_POOL_TYPE = "nfs"

    def __init__(self, pool_config):
        super().__init__(pool_config)
        spec = pool_config["spec"]
        self._nfs_server = spec["server"]
        self._export_dir = spec["export"]
        self._nfs_access = _NfsPoolAccess(spec)
        self._mnt = spec["mount"]

    def open(self):
        src = f"{self._nfs_server}:{self._export_dir}"
        dst = self.mnt
        init_dir(dst)
        options = str(self._nfs_access)
        utils_misc.mount(src, dst, "nfs", options)

    def close(self):
        src = f"{self._nfs_server}:{self._export_dir}"
        dst = self._mnt
        utils_misc.umount(src, dst, "nfs")

    def connected(self):
        src = f"{self._nfs_server}:{self._export_dir}"
        dst = self.mnt
        return utils_misc.is_mount(src, dst, fstype="nfs")

    @property
    def mnt(self):
        return self._mnt
