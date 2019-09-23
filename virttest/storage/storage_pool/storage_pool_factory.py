
from virttest.storage.utils import utils_misc
from virttest.storage.storage_volume import exception
from virttest.storage.storage_pool import storage_pool


class StoragePoolFactory(object):

    pools = {}

    @classmethod
    def produce(cls, name, protocol, params):
        support_protocols = storage_pool.SUPPORTED_STORAGE_POOLS.keys()
        if protocol not in support_protocols:
            raise ValueError(
                "Unknown protocol '%s'! supported protocols are: %s" %
                (protocol, support_protocols))
        cls_storage_pool = storage_pool.SUPPORTED_STORAGE_POOLS.get(protocol)
        pool = cls_storage_pool(name, params)
        return pool

    @classmethod
    def list_all_pools(cls):
        return cls.pools.values()

    @classmethod
    def get_pool_by_name(cls, name):
        if name not in cls.pools.keys():
            return None
        else:
            return cls.pools[name]

    @classmethod
    def create_storage_pool(cls, pool):
        pool.create()
        cls.pools[pool.name] = pool

    @classmethod
    def list_volumes(cls, pool_name):
        pool = cls.pools.get(pool_name)
        if pool is None:
            return list()
        else:
            return pool.volumes.values()

    @classmethod
    def get_volume_by_name(cls, sp_name, vol_name):
        pool = cls.get_pool_by_name(sp_name)
        if pool is None:
            return None
        else:
            return pool.volumes.get(vol_name)

    @staticmethod
    def format_volume(vol):
        vol_fmt = vol.fmt.type
        if vol_fmt == "qcow2":
            return utils_misc.format_volume_to_qcow2(vol)
        elif vol_fmt == "luks":
            return utils_misc.format_volume_to_luks(vol)
        elif vol_fmt == "raw":
            return utils_misc.format_volume_to_raw(vol)
        else:
            raise exception.UnsupportedVolumeFormatException(vol_fmt)

    @staticmethod
    def allocate_volume(vol):
        return vol.storage_pool.accocate_volume(vol)
