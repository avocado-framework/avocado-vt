import logging
import os

from avocado.utils import process

from virttest import utils_misc

from ...backing import _ResourceBacking

LOG = logging.getLogger("avocado.service." + __name__)


class _DirVolumeBacking(_ResourceBacking):
    RESOURCE_TYPE = "volume"
    RESOURCE_POOL_TYPE = "filesystem"

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

    def create_object(self, pool_connection):
        """
        Create the backing object
        """
        if not self._uri:
            self._uri = os.path.join(pool_connection.root_dir, self._filename)

    def allocate_resource(self, pool_connection, arguments=None):
        dir_name = os.path.dirname(self._uri)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)

        # TODO: add io drivers
        cmd = ""
        how = arguments.pop("how", "fallocate") if arguments else "fallocate"
        if how == "copy":
            source = arguments.pop("source")
            cmd = f"cp -rp {source} {self._uri}"
        elif how == "fallocate":
            cmd = f"fallocate -x -l {self._size} {self._uri}"

        process.run(
            cmd,
            shell=True,
            verbose=False,
            ignore_status=False,
        )

        self._resource_allocated = True
        return self.sync_resource_info(pool_connection)

    def release_resource(self, pool_connection, arguments=None):
        if os.path.exists(self._uri):
            os.unlink(self._uri)
        self._resource_allocated = False

    def clone_resource(self, pool_connection, arguments=None):
        postfix = utils_misc.generate_random_string(8)
        filename = f"{self._filename}_{postfix}"
        uri = f"{self._uri}_{postfix}"

        def_clone_cmd = f"cp -rp {self._uri} {uri}"
        process.run(
            def_clone_cmd,
            shell=True,
            verbose=False,
            ignore_status=False,
        )

        s = os.stat(uri)
        allocation = s.st_size
        return {
            "meta": {
                "allocated": self._resource_allocated,
            },
            "spec": {
                "uri": uri,
                "filename": filename,
                "allocation": allocation,
            },
        }

    def sync_resource_info(self, pool_connection, arguments=None):
        allocation = None
        try:
            s = os.stat(self._uri)
            allocation = s.st_size
        except FileNotFoundError:
            self._resource_allocated = False

        return {
            "meta": {
                "allocated": self._resource_allocated,
            },
            "spec": {
                "uri": self._uri,
                "allocation": allocation,
            },
        }

    def resize_volume(self, pool_connection, arguments=None):
        pass
