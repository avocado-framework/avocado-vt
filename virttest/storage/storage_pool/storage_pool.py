import os
import rados
from gluster import gfapi

from virttest import utils_disk
from virttest.storage.utils import utils_misc
from virttest.storage.utils import iscsicli


class BasePool(object):

    protocol = "none"
    pool_base_dir = utils_misc.make_pool_base_dir(protocol)

    def __init__(self, name):
        self.root_dir = os.path.join(self.pool_base_dir, name)
        self.name = name
        self.volumes = dict()
        self.available = None

    def create(self):
        raise NotImplementedError

    def refresh(self):
        raise NotImplementedError

    def destroy(self):
        raise NotImplementedError

    def exists(self):
        return os.path.exists(self.root_dir)

    def remove(self):
        if self.exists():
            os.removedirs(self.root_dir)

    def list_volumes(self):
        pass

    def list_volume_names(self):
        pass

    def get_volume_by_name(self, name):
        return self.volumes.get(name) 

    def allocate_volume(self, vol):
        return vol


class FilePool(BasePool):

    protocol = "file"
    pool_base_dir = utils_misc.make_pool_base_dir(protocol)

    def __init__(self, name, params):
        super(FilePool, self).__init__(name)
        self.path = params["path"]

    def create(self):
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        if os.path.exists(self.root_dir):
            os.remove(self.root_dir)
        os.symlink(self.path, self.root_dir)

    def refresh(self):
        pass

    def destroy(self):
        self.remove()

    def list_files(self):
        return utils_misc.list_files(self.root_dir)


class GlusterPool(FilePool):

    protocol = "gluster"
    pool_base_dir = utils_misc.make_pool_base_dir(protocol)

    def __init__(self, name, params):
        super(GlusterPool, self).__init__(name, params)
        self.host = params["gluster_host"]
        self.dir_path = params["gluster_dir"]
        self.volume_name = params["gluster_volume"]
        self.debug = params.get("debug")
        self.logfile = params.get("logfile")
        self._volume = None

    def create(self):
        volume = gfapi.Volume(self.host, self.volume_name)
        volume.mount()
        volume.mkdir(self.dir_path)
        self._volume = volume

    def list_files(self):
        return utils_misc.list_files_in_gluster_volume(
            self._volume, self.dir_path)

    def destroy(self):
        if self._volume.mounted:
            self._volume.umount()


class IscsiDriectPool(FilePool):

    protocol = "iscsi"
    pool_base_dir = utils_misc.make_pool_base_dir(protocol)

    def __init__(self, name, params):
        super(IscsiDriectPool, self).__init__(name, params)
        portal = params.get("portal", "")
        if ":" in portal:
            self.host = portal.split(':')[0]
            self.port = portal.split(':')[1]

        else:
            self.host = params["iscsi_host"]
            self.port = params.get("iscsi_port", "3260")

        self.transport = params.get("transport", "tcp")
        self.portal = ":".join([self.host, self.port])
        self.initiator = params["iscsi_initiator"]
        self.target = params["iscsi_target"]
        self.user = params.get("iscsi_user")
        self.password_secret = params.get("iscsi_password_secret")
        self.header_digest = params.get("iscsi_header_digest")
        self.timeout = params.get("iscsi_timeout")
        self.cli = iscsicli.IscsiCli(
            self.host, self.port, self.initiator, self.target)

    def create(self):
        self.cli.login()

    def list_files(self):
        return map(str, self.cli.list_luns())

    def destroy(self):
        self.cli.logout()


class NfsPool(FilePool):

    protocol = "nfs"
    pool_base_dir = utils_misc.make_pool_base_dir(protocol)

    def __init__(self, name, params):
        super(NfsPool, self).__init__(name, params)
        self.dir_path = params["nfs_dir"]
        self.hostname = params["nfs_host"]
        self.src_dir = ":".join([params["nfs_host"], params["nfs_dir"]])
        self.user = params.get("nfs_user")
        self.group = params.get("nfs_group")
        self.tcp_sync_count = params.get("nfs_tcp_sync_count")
        self.readahead_size = params.get("nfs_readahead_size")
        self.page_cache_size = params.get("nfs_page_cache_size")
        self.debug = params.get("nfs_debug_level")

    def create(self):
        if not os.path.exists(self.root_dir):
            os.mkdir(self.root_dir)
        if not utils_disk.is_mount(self.src_dir, self.root_dir, self.protocol):
            utils_disk.umount(self.src_dir, self.root_dir, self.protocol)
        utils_disk.mount(self.src_dir, self.root_dir, self.protocol)

    def destroy(self):
        if utils_disk.is_mount(self.src_dir, self.root_dir, self.protocol):
            utils_disk.umount(self.src_dir, self.root_dir, self.protocol)


class RbdPool(FilePool):

    protocol = 'rbd'
    pool_base_dir = utils_misc.make_pool_base_dir(protocol)

    def __init__(self, name, params):
        super(RbdPool, self).__init__(name, params)
        self.host = params["rbd_host"]
        self.port = params("rbd_port")
        self.conf = params.get("rbd_conf")
        self.snapshot = params.get("rdb_snapshot")
        self.user = params.get("rdb_user")
        self.key_secret = params.get("rdb_key_secret")
        self.auth_client_required = params.get("rdb_auth_client_required")
        self._cluster = None

    def create(self):
        self._cluster = rados.Rados(conffile=self.conf)
        self._cluster.connect()

    def destroy(self):
        self._cluster.shutdown()

    def list_pools(self):
        return self._cluster.list_pools()

    def create_pool(self, pool_name):
        self._cluster.create_pool(pool_name)

    def delete_pool(self, pool_name):
        self._cluster.delete_pool(pool_name)


SUPPORTED_STORAGE_POOLS = {
    "file": FilePool,
    "nfs": NfsPool,
    "gluster": GlusterPool,
    "rbd": RbdPool,
    "iscsi": IscsiDriectPool
}
