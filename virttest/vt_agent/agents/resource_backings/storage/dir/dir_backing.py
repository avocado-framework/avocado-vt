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
        self._uri = None
        self._handlers.update({
            "resize": self.resize_volume,
        })

    def create(self, pool_connection):
        self._uri = os.path.join(pool_connection.root_dir, self._filename)

    def destroy(self, pool_connection):
        self._uri = None

    def allocate_resource(self, pool_connection, arguments):
        dirname = os.path.dirname(self._uri)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        size = self._size
        cmd_result = process.run(
            f"fallocate -l {size} {self._uri}",
            shell=True, verbose=False, ignore_status=False
        )

        r, o = cmd_result.exit_status, dict()
        if r != 0:
            o["out"] = cmd_result.stderr_text
        else:
            o["out"] = self.info_resource(pool_connection)

        return r, o

    def release_resource(self, pool_connection, arguments):
        r, o = 0, dict()

        try:
            os.unlink(self._uri)
        except Exception as e:
            o["error"] = str(e)

        return r, o

    def resize_volume(self, pool_connection, arguments):
        pass

    def info_resource(self, pool_connection):
        allocated = True
        allocation = 0

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
        r, o = 0, dict()
        try:
            o["out"] = self.info_resource(pool_connection)
        except Exception as e:
            r, o["out"] = 1, str(e)

        return r, o
