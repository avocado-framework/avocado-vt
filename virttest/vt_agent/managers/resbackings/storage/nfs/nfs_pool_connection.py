import utils_disk

from ...pool_connection import _ResourcePoolAccess
from ...pool_connection import _ResourcePoolConnection


class _NfsPoolAccess(_ResourcePoolAccess):
    """
    Mount options
    """

    def __init__(self, pool_access_config):
        self._options = pool_access_config['nfs_options']

    def __str__(self):
        return self._options


class _NfsPoolConnection(_ResourcePoolConnection):

    def __init__(self, pool_config, pool_access_config):
        super().__init__(pool_config, pool_access_config)
        self._connected_pool = pool_config['pool_id']
        self._nfs_server = pool_config['nfs_server']
        self._export_dir = pool_config['export_dir']
        self._nfs_access = _NfsPoolAccess(pool_access_config)
        self._mnt = pool_config.get(nfs_mnt_dir)
        if self._mnt is None:
            self._create_default_mnt()

    def startup(self):
        src = '{host}:{export}'.format(self._nfs_server, self._export_dir)
        dst = self._mnt
        options = str(self._nfs_access)
        utils_disk.mount(src, dst, fstype='nfs', options=options)

    def shutdown(self):
        src = '{host}:{export}'.format(self._nfs_server, self._export_dir)
        dst = self._mnt
        utils_disk.umount(src, dst, fstype='nfs')

    def connected(self):
        src = '{host}:{export}'.format(self._nfs_server, self._export_dir)
        dst = self._mnt
        return utils_disk.is_mount(src, dst, fstype='nfs')

    @property
    def mnt(self):
        return self._mnt
