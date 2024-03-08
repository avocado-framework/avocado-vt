import logging
import os

from avocado.utils import process

from ...backing import _ResourceBacking


LOG = logging.getLogger("avocado.agents.resource_backings.storage.dir" + __name__)


class _DirVolumeBacking(_ResourceBacking):
    _SOURCE_POOL_TYPE = "filesystem"
    _BINDING_RESOURCE_TYPE = "volume"

    def __init__(self, backing_config):
        super().__init__(backing_config)
        self._size = backing_config["spec"]["size"]
        self._filename = backing_config["spec"]["filename"]
        self._uri = backing_config["spec"].get("uri")
        self._handlers.update({
            "resize": self.resize_volume,
        })

    def create(self, pool_connection):
        if not self._uri:
            self._uri = os.path.join(pool_connection.root_dir, self._filename)

    def destroy(self, pool_connection):
        super().destroy(pool_connection)
        self._uri = None

    def allocate_resource(self, pool_connection, arguments):
        dirname = os.path.dirname(self._uri)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        process.run(
            f"fallocate -l {self._size} {self._uri}",
            shell=True, verbose=False, ignore_status=False
        )

        return self.info_resource(pool_connection)

    def release_resource(self, pool_connection, arguments):
        if os.path.exists(self._uri):
            os.unlink(self._uri)

    def resize_volume(self, pool_connection, arguments):
        pass

    def info_resource(self, pool_connection):
        allocated, allocation = True, 0

        try:
            s = os.stat(self._uri)
            allocation = str(s.st_size)
        except FileNotFoundError:
            allocated = False

        return {
            "meta": {
                "allocated": allocated,
            },
            "spec": {
                "uri": self._uri,
                "allocation": allocation,
            }
        }

    def sync_resource(self, pool_connection, arguments):
        return self.info_resource(pool_connection)
