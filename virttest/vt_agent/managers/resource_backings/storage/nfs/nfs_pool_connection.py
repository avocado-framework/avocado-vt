import logging
import os

from avocado.utils.path import init_dir
from virttest import utils_disk
from vt_agent.core.data_dir import get_data_dir

from ...pool_connection import _ResourcePoolConnection

LOG = logging.getLogger("avocado.service." + __name__)


class _NfsPoolConnection(_ResourcePoolConnection):
    POOL_TYPE = "nfs"

    def __init__(self, pool_config):
        super().__init__(pool_config)
        spec = pool_config["spec"]
        self._server = spec["server"]
        self._export_dir = spec["export"]
        self._mnt_opts = spec.get("mount-options") or "rw"
        self._mnt = spec.get("mount") or os.path.join(get_data_dir(), f"nfs_mnt/{self._server}")

    def open(self):
        src = f"{self._server}:{self._export_dir}"
        dst = self.mnt
        init_dir(dst)
        utils_disk.mount(src, dst, fstype="nfs", options=self._mnt_opts)

        return {
            "spec": {
                "mount": self.mnt,
                "mount-options": self.mnt_opts,
            }
        }

    def close(self):
        src = f"{self._server}:{self._export_dir}"
        dst = self._mnt
        utils_disk.umount(src, dst, fstype="nfs")

    def connected(self):
        src = f"{self._server}:{self._export_dir}"
        dst = self.mnt
        return utils_disk.is_mount(src, dst, fstype="nfs")

    @property
    def mnt(self):
        return self._mnt

    @property
    def mnt_opts(self):
        return self._mnt_opts
