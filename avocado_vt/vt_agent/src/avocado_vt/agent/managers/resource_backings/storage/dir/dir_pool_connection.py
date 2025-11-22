import os

from avocado.utils.path import init_dir

# pylint: disable=E0611
from avocado_vt.agent.core.data_dir import get_data_dir

from ...pool_connection import ResourcePoolConnection


# TODO: Add StoragePoolConnection, FilePoolConnection
class DirPoolConnection(ResourcePoolConnection):
    POOL_TYPE = "filesystem"

    def __init__(self, pool_config):
        super().__init__(pool_config)
        root_dir = pool_config["spec"]["path"] or "root_dir"
        if not os.path.isabs(root_dir):
            root_dir = os.path.abspath(os.path.join(get_data_dir(), root_dir))
        self.root_dir = os.path.realpath(root_dir)

    def open(self):
        init_dir(self.root_dir)
        return {
            "spec": {
                "path": self.root_dir,
            }
        }

    def close(self):
        if not os.listdir(self.root_dir):
            os.removedirs(self.root_dir)

    @property
    def connected(self):
        return os.path.exists(self.root_dir)

    @property
    def root_dir(self):
        return self._root_dir

    @root_dir.setter
    def root_dir(self, root_dir):
        self._root_dir = root_dir
