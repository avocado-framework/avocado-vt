import utils_disk

from ...pool_connection import _ResourcePoolConnection


class _DirPoolConnection(_ResourcePoolConnection):

    def __init__(self, pool_config, pool_access_config):
        super().__init__(pool_config, pool_access_config)
        self._dir = pool_config.get('root_dir')
        if self._mnt is None:
            self._create_default_dir()

    def startup(self):
        pass

    def shutdown(self):
        pass

    def connected(self):
        return os.path.exists(self.dir)

    @property
    def dir(self):
        return self._dir
