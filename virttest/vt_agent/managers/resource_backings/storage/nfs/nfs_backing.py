import logging
import os

from avocado.utils import process

from ...backing import _ResourceBacking

LOG = logging.getLogger("avocado.service." + __name__)


class _NfsVolumeBacking(_ResourceBacking):
    _SOURCE_POOL_TYPE = "nfs"
    _BINDING_RESOURCE_TYPE = "volume"

    def __init__(self, backing_config):
        super().__init__(backing_config)
        self._size = backing_config["spec"]["size"]
        self._filename = backing_config["spec"]["filename"]
        self._uri = backing_config["spec"].get("uri")
        self._handlers.update(
            {
                "resize": self.resize_volume,
            }
        )

    def create(self, pool_connection):
        if not self._uri:
            self._uri = os.path.join(pool_connection.mnt, self._filename)

    def destroy(self, pool_connection):
        super().destroy(pool_connection)
        self._uri = None

    def allocate_resource(self, pool_connection, arguments=None):
        dirname = os.path.dirname(self._uri)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        # FIXME: handlers
        how = None
        if arguments is not None:
            how = arguments.pop("how", "fallocate")
        cmd = ""
        if how == "copy":
            source = arguments.pop("source")
            cmd = f"cp -rp {source} {self._uri}"
        elif how == "fallocate":
            cmd = f"fallocate -x -l {self._size} {self._uri}"

        try:
            process.run(
                cmd,
                shell=True,
                verbose=False,
                ignore_status=False,
            )
        except Exception:
            self.release_resource(pool_connection)
            raise

        return self.get_resource_info(pool_connection)

    def release_resource(self, pool_connection, arguments=None):
        if os.path.exists(self._uri):
            os.unlink(self._uri)

    def resize_volume(self, pool_connection, arguments):
        pass

    def get_resource_info(self, pool_connection, arguments=None):
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
            },
        }
