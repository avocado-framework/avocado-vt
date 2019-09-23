import logging
from functools import reduce

from virttest.virt_storage import exception
from virttest.virt_storage import storage_volume
from virttest.virt_storage import virt_encryption
from virttest.virt_storage.backend import directory, direct_iscsi, nfs, rbd, gluster
from virttest.virt_storage.utils import state


class StoragePoolAdmin(object):
    supported_storage_backend = {
        "directory": directory.DirectoryPool,
        "nfs": nfs.NfsPool,
        "gluster": gluster.GlusterPool,
        "iscsi-direct": direct_iscsi.IscsiDriectPool,
        "rbd": rbd.RbdPool
    }

    __pools = set()

    @classmethod
    def _find_storage_driver(cls, backend_type):
        try:
            return cls.supported_storage_backend[backend_type]
        except KeyError:
            raise exception.UnsupportedStoragePoolException(cls, backend_type)

    @classmethod
    def pool_define_by_params(cls, name, params):
        """
        Define logical storage pool object by test params,
        initial status of the pool is dead.

        :param params:  pool params object
        :param name: storage pool name

        :return StoragePool object
        """
        driver = cls._find_storage_driver(params["storage_type"])
        pool = driver.pool_define_by_params(name, params)
        pool.refresh()
        state.register_pool_state_machine(pool)
        cls.__pools.add(pool)
        return pool

    @classmethod
    def pools_define_by_params(cls, params):
        lst_names = params.objects("storage_pools")
        lst_params = map(params.object_params, lst_names)
        return map(lambda x: cls.pool_define_by_params(
            *x), zip(lst_names, lst_params))

    @classmethod
    def list_volumes(cls):
        """List all volumes in host"""
        return reduce(lambda x, y: x.union(
            y), [p.get_volumes() for p in sp_admin.list_pools()])

    @classmethod
    def list_pools(cls):
        return cls.__pools

    @classmethod
    def find_pool_by_name(cls, name):
        for pool in cls.__pools:
            if pool.name == name:
                return pool
        return None

    @staticmethod
    def find_pool_by_volume(volume):
        return volume.pool

    @classmethod
    def find_pool_by_path(cls, path):
        try:
            return filter(lambda x: x.target.path == path, cls.list_pools())[0]
        except IndexError:
            logging.warn("no storage pool with matching path '%s'" % path)
        return None

    @staticmethod
    def start_pool(pool):
        return pool.start_pool()

    @staticmethod
    def stop_pool(pool):
        return pool.stop_pool()

    @staticmethod
    def destroy_pool(pool):
        return pool.destroy_pool()

    @staticmethod
    def refresh_pool(pool):
        return pool.refresh()

    @classmethod
    def release_volume(cls, volume):
        pool = cls.find_pool_by_volume(volume)
        pool.release_volume(volume)

    @classmethod
    def volumes_define_by_params(cls, params):
        return map(lambda x: cls.volume_define_by_params(
            x, params), params.objects("images"))

    @classmethod
    def volume_define_by_params(cls, volume_name, test_params):
        """
        params: full test params
        """

        def _get_pool_by_params(name, pool_params):
            """Get pool by params if it's really defined return it else define a new pool"""
            pool = cls.find_pool_by_name(name)
            if not pool:
                pool = cls.pool_define_by_params(name, pool_params)
            return pool

        def _get_volume_by_params(pool, name, volume_params):
            """Get volume object by test params if it's defined else return a new volume"""
            volume = None
            if pool.TYPE == "iscsi-direct":
                url = volume_params.get("image_url")
                if url:
                    volume = cls.get_volume_by_url(url)
            elif pool.TYPE in ("gluster", "nfs"):
                url = volume_params.get("image_url")
                if not url:
                    url = pool.helper.get_url_by_name(name)
                if url:
                    volume = cls.get_volume_by_url(url)
            elif pool.TYPE == "directory":
                path = volume_params.get("image_path")
                if not path:
                    path = pool.helper.get_path_by_name(name)
                if path:
                    volume = cls.get_volume_by_path(path)
            if not volume:
                volume = storage_volume.StorageVolume(pool, name=name)
            return volume

        def _volume_define_by_params(name, params):
            """Get volume object by params"""

            volume_params = params.object_params(name)
            pool_name = volume_params.get("storage_pool")
            pool_params = params.object_params(pool_name)
            pool = _get_pool_by_params(pool_name, pool_params)
            volume = _get_volume_by_params(pool, name, volume_params)
            volume.name = name
            volume.format = volume_params.get("image_format", "raw")
            volume.capacity = volume_params.get("image_size", "100M")
            volume.preallocation = volume_params.get("preallocation", "off")

            encryption_on = volume_params.get(
                "image_encryption", "off") != "off"
            if encryption_on:
                encryption = virt_encryption.VolumeEncryption.encryption_define_by_params(
                    volume_params)
                volume.encryption = encryption

            backing_name = volume_params.get("backing", None)
            if backing_name:
                backing_store = cls.get_volume_by_name(backing_name)
                if not backing_store:
                    backing_store = _volume_define_by_params(
                        backing_name, params)
                volume.backing_store = backing_store
            else:
                volume.backing_store = None
            return volume

        return _volume_define_by_params(volume_name, test_params)

    @classmethod
    def acquire_volume(cls, volume):
        def _acquire_volume(vol):
            if vol.is_allocated:
                return
            if vol.backing_store:
                _acquire_volume(vol.backing_store)
            pool = cls.find_pool_by_volume(vol)
            pool.acquire_volume(vol)

        _acquire_volume(volume)

    @classmethod
    def remove_volume(cls, volume):
        pool = cls.find_pool_by_volume(volume)
        pool.remove_volume(volume)

    @classmethod
    def get_volume_by_name(cls, name):
        volumes = filter(lambda x: x.name == name, cls.list_volumes())
        return volumes[0] if volumes else None

    @classmethod
    def get_volume_by_path(cls, path):
        volumes = filter(lambda x: x.path == path, cls.list_volumes())
        return volumes[0] if volumes else None

    @classmethod
    def get_volume_by_url(cls, url):
        volumes = filter(lambda x: x.url == url, cls.list_volumes())
        return volumes[0] if volumes else None


sp_admin = StoragePoolAdmin()
